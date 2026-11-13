local wezterm = require("wezterm")
local palettes = require("lua.palettes")

local M = {}
-- Weak keys ensure pane-scoped state is released automatically when panes die.
local pane_theme_modes = setmetatable({}, { __mode = "k" })

-- Theme contract:
-- 1. ~/.local/state/dotfiles/theme is the persisted global default for new tabs/shells.
-- 2. a pane may publish a live `theme_mode` user var to override its current tab.
-- 3. WezTerm stores the resolved per-tab theme in tab config overrides.
M.default_theme_file = wezterm.home_dir .. "/.local/state/dotfiles/theme"

function M.read_default_theme_mode()
   local f = io.open(M.default_theme_file, "r")
   if not f then
      return "dark"
   end

   local mode = f:read("*l")
   f:close()

   if mode == "light" then
      return "light"
   end

   if mode == "dark" then
      return "dark"
   end

   return "dark"
end

function M.normalize_mode(mode)
   if mode == "light" then
      return "light"
   end

   return "dark"
end

function M.parse_mode(mode)
   if mode == "light" or mode == "dark" then
      return mode
   end

   return nil
end

function M.get_palette(mode)
   return palettes.get(M.normalize_mode(mode))
end

function M.get_colors(mode)
   local palette = M.get_palette(mode)

   return {
      foreground = palette.foreground,
      background = palette.background,

      ansi = palette.ansi,
      brights = palette.brights,

      cursor_bg = palette.cursor_bg,
      cursor_fg = palette.cursor_fg,
      cursor_border = palette.cursor_border,

      selection_fg = palette.selection_fg,
      selection_bg = palette.selection_bg,

      tab_bar = {
         background = palette.tab_bar_bg,

         active_tab = {
            bg_color = palette.tab_active_bg,
            fg_color = palette.tab_active_fg,
            intensity = "Bold",
         },

         inactive_tab = {
            bg_color = palette.tab_inactive_bg,
            fg_color = palette.tab_inactive_fg,
         },

         inactive_tab_hover = {
            bg_color = palette.tab_hover_bg,
            fg_color = palette.tab_hover_fg,
            italic = false,
         },

         new_tab = {
            bg_color = palette.tab_inactive_bg,
            fg_color = palette.tab_inactive_fg,
         },

         new_tab_hover = {
            bg_color = palette.tab_hover_bg,
            fg_color = palette.tab_hover_fg,
         },
      },
   }
end

function M.read_tab_theme_mode(window, tab)
   if not window or not tab then
      return nil
   end

   -- Tab overrides are the persisted source of truth for per-tab theme memory.
   local ok, overrides = pcall(function()
      return window:effective_tab_config_overrides(tab)
   end)

   if not ok then
      ok, overrides = pcall(function()
         return window:get_tab_config_overrides(tab)
      end)
   end

   if not ok or type(overrides) ~= "table" then
      return nil
   end

   if overrides.theme_mode then
      return M.normalize_mode(overrides.theme_mode)
   end

   return nil
end

function M.read_live_pane_theme_mode(pane)
   if not pane then
      return nil
   end

   -- Live user vars let the current shell/editor temporarily steer the tab theme.
   local remembered_mode = pane_theme_modes[pane]
   if remembered_mode then
      return remembered_mode
   end

   local vars = pane:get_user_vars()
   if vars.theme_mode then
      local mode = M.parse_mode(vars.theme_mode)
      if mode then
         pane_theme_modes[pane] = mode
         return mode
      end
   end

   return nil
end

function M.get_target_tab(window, pane)
   if pane then
      local ok, tab = pcall(function()
         return pane:tab()
      end)
      if ok and tab then
         return tab
      end
   end

   if window then
      local ok, tab = pcall(function()
         return window:active_tab()
      end)
      if ok and tab then
         return tab
      end
   end

   return nil
end

function M.resolve_runtime_theme(window, pane)
   -- Runtime precedence is: live pane request -> stored tab override -> global default.
   local live_pane_mode = M.read_live_pane_theme_mode(pane)
   if live_pane_mode then
      return live_pane_mode, "pane"
   end

   local tab = M.get_target_tab(window, pane)
   local tab_mode = M.read_tab_theme_mode(window, tab)
   if tab_mode then
      return tab_mode, "tab"
   end

   return M.read_default_theme_mode(), "default"
end

function M.apply_window_theme_mode(window, mode)
   if not window then
      return false
   end

   local overrides = window:get_config_overrides() or {}

   if overrides.theme_mode == mode and overrides.colors ~= nil then
      return false
   end

   overrides.theme_mode = mode
   overrides.colors = M.get_colors(mode)
   window:set_config_overrides(overrides)
   return true
end

function M.apply_tab_theme_mode(window, tab, mode)
   if not window or not tab then
      return nil
   end

   local ok, overrides = pcall(function()
      return window:get_tab_config_overrides(tab)
   end)

   if not ok then
      return nil
   end

   if type(overrides) ~= "table" then
      overrides = {}
   end

   overrides.set_environment_variables = overrides.set_environment_variables or {}
   local has_runtime_env = overrides.set_environment_variables.ZSH_THEME_MODE == mode
      and overrides.set_environment_variables.NVIM_THEME == mode

   if overrides.theme_mode == mode and overrides.colors ~= nil and has_runtime_env then
      return false
   end

   overrides.theme_mode = mode
   overrides.colors = M.get_colors(mode)
   overrides.set_environment_variables.ZSH_THEME_MODE = mode
   overrides.set_environment_variables.NVIM_THEME = mode
   window:set_tab_config_overrides(tab, overrides)
   return true
end

function M.apply_runtime_theme_mode(window, pane, mode, source)
   -- A new tab starts with the window palette before its shell publishes a
   -- pane-specific mode. Keep that base palette at the current global default.
   M.apply_window_theme_mode(window, M.read_default_theme_mode())

   mode = M.normalize_mode(mode)
   source = source or "pane"

   if source == "default" then
      return M.apply_window_theme_mode(window, mode)
   end

   local tab = M.get_target_tab(window, pane)
   if tab then
      local changed = M.apply_tab_theme_mode(window, tab, mode)
      if changed ~= nil then
         return changed
      end
   end

   return M.apply_window_theme_mode(window, mode)
end

function M.sync_window_theme(window, pane)
   local mode, source = M.resolve_runtime_theme(window, pane)
   return M.apply_runtime_theme_mode(window, pane, mode, source)
end

function M.apply_resolved_theme(window, pane, mode)
   if mode ~= nil then
      return M.apply_runtime_theme_mode(window, pane, mode, "pane")
   end

   return M.sync_window_theme(window, pane)
end

function M.setup(wezterm)
   wezterm.on("user-var-changed", function(window, pane, name, value)
      if name ~= "theme_mode" then
         return
      end

      local mode = M.parse_mode(value)
      if not mode then
         return
      end

      pane_theme_modes[pane] = mode
      M.apply_resolved_theme(window, pane, mode)
   end)

   wezterm.on("window-config-reloaded", function(window, pane)
      M.apply_resolved_theme(window, pane)
   end)

   wezterm.on("window-focus-changed", function(window, pane)
      M.apply_resolved_theme(window, pane)
   end)
end

return M

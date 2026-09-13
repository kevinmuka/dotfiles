local M = {}

local function is_blocked(binding, wezterm)
   local action = wezterm.to_string(binding.action)
   return action:find("Spawn", 1, true) ~= nil
      or action:find("Split", 1, true) ~= nil
      or action:find("ActivateCommandPalette", 1, true) ~= nil
      or action:find("ShowLauncher", 1, true) ~= nil
      or action:find("AttachDomain", 1, true) ~= nil
      or action:find("DetachDomain", 1, true) ~= nil
      or action:find("SwitchToWorkspace", 1, true) ~= nil
end

local function is_enabled()
   return os.getenv("NEOVIM_APP_SINGLE_SESSION") == "1"
end

function M.apply(config, wezterm)
   if not is_enabled() then
      return
   end

   config.enable_tab_bar = false
   config.show_new_tab_button_in_tab_bar = false
   config.disable_default_key_bindings = true

   local allowed_keys = {}
   if wezterm.gui then
      for _, binding in ipairs(wezterm.gui.default_keys()) do
         if not is_blocked(binding, wezterm) then
            table.insert(allowed_keys, binding)
         end
      end
   end
   for _, binding in ipairs(config.keys or {}) do
      if not is_blocked(binding, wezterm) then
         table.insert(allowed_keys, binding)
      end
   end
   config.keys = allowed_keys

   wezterm.on("new-tab-button-click", function()
      return false
   end)
end

return M

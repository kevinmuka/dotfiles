local wezterm = require("wezterm")
local act = wezterm.action
local config = {}

local theme = require("lua.theme")
local keys = require("lua.keys")
local ui = require("lua.ui")
local plugins = require("lua.plugins")
local neovim_app = require("lua.neovim_app")

local default_theme_mode = theme.read_default_theme_mode()
local palette = theme.get_palette(default_theme_mode)

ui.apply(config, wezterm)

config.keys = keys.get(wezterm, act)
config.colors = theme.get_colors(default_theme_mode)

plugins.setup(config, wezterm, act, palette)
theme.setup(wezterm)
neovim_app.apply(config, wezterm)

return config

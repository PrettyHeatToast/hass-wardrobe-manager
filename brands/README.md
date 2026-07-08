# Brand assets

These are the brand icons for the `wardrobe` integration, used by the Home Assistant
frontend (integrations page, device cards, config flow dialogs).

Home Assistant only loads brand icons from the central
[home-assistant/brands](https://github.com/home-assistant/brands) repository — they
cannot be served from the integration itself. To get the icon shown:

1. Fork https://github.com/home-assistant/brands
2. Copy `brands/wardrobe/icon.png` (256x256) and `brands/wardrobe/icon@2x.png`
   (512x512) into `custom_integrations/wardrobe/` in the fork
3. Open a pull request against the brands repository

Until that PR is merged, Home Assistant shows a generic puzzle-piece icon for this
integration. That is expected and cannot be overridden locally.

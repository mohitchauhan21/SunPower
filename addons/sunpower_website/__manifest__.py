{
    "name": "SunPower Website",
    "version": "18.0.1.0.0",
    "summary": "Public website, savings estimator, customer solar portal and "
               "technician view for SunPower Solar",
    "category": "Website",
    "author": "SunPower Hackathon Team",
    "license": "LGPL-3",
    "depends": ["sunpower_solar", "website", "portal", "auth_signup", "auth_oauth"],
    "data": [
        "data/auth_settings.xml",
        "data/auth_providers.xml",
        "views/layout.xml",
        "views/home.xml",
        "views/estimate.xml",
        "views/portal.xml",
        "views/technician.xml",
        "views/menus.xml",
        "views/branding.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "sunpower_website/static/src/scss/sunpower_website.scss",
            "sunpower_website/static/src/js/estimate.js",
        ],
    },
    "installable": True,
    "application": False,
}

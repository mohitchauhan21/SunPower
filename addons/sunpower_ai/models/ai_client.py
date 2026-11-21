import base64
import logging
import os

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
TIMEOUT = 70


class SolarAiClient(models.AbstractModel):
    _name = "solar.ai.client"
    _description = "SunPower AI service client"

    @api.model
    def _base_url(self):
        return (self.env["ir.config_parameter"].sudo().get_param("sunpower_ai.url")
                or os.environ.get("AI_SERVICE_URL") or "http://localhost:8000").rstrip("/")

    @api.model
    def call(self, path, data=None, files=None, json=None):
        """POST to the AI service. Returns the JSON dict on success; raises a
        friendly UserError (manual entry still possible) on any failure."""
        url = self._base_url() + path
        try:
            r = requests.post(url, data=data, files=files, json=json, timeout=TIMEOUT)
            body = r.json()
        except requests.exceptions.ConnectionError:
            raise UserError(_("The AI assistant is not running right now. "
                              "Please fill in the details manually."))
        except requests.exceptions.Timeout:
            raise UserError(_("The AI assistant took too long. "
                              "Please fill in the details manually."))
        except Exception as e:
            _logger.exception("AI call failed")
            raise UserError(_("AI assistant error (%s). Please fill in the details manually.", e))
        if not body.get("ok"):
            err = body.get("error") or {}
            raise UserError(_("The AI assistant could not help with this one (%(m)s). "
                              "Please fill in the details manually.",
                              m=err.get("message") or err.get("code")))
        return body

    @api.model
    def file_tuple(self, b64data, filename, mimetype="application/octet-stream"):
        return (filename or "upload", base64.b64decode(b64data), mimetype)

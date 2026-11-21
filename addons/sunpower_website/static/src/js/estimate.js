/* SunPower estimate page: live recalculation + optional AI bill upload.
 * Plain script (no Odoo module system needed). Manual entry always works;
 * the page also works without JS via the GET form. */
(function () {
    "use strict";

    function init() {
        var root = document.getElementById("sp_estimator");
        if (!root) { return; }
        var cfg = JSON.parse(root.dataset.cfg || "{}");
        var aiUrl = root.dataset.aiUrl || "http://localhost:8000";
        var $ = function (id) { return document.getElementById(id); };
        var units = $("sp_units"), bill = $("sp_bill");

        // Hide the no-JS submit button: results update as you type.
        root.querySelectorAll(".sp-nojs").forEach(function (b) { b.classList.add("d-none"); });

        function subsidy(kw) { return Math.min(kw, 2) * 30000 + (kw >= 3 ? 18000 : 0); }
        function fmt(n) { return Math.round(n).toLocaleString("en-IN"); }

        function compute() {
            var u = parseFloat(units.value) || 0;
            var b = parseFloat(bill.value) || 0;
            var m = u || (b ? b / cfg.tariff : 0);
            if (!m) { return null; }
            var kw = Math.min(Math.max(Math.round(m / cfg.unitsPerKw), cfg.minKw), cfg.maxKw);
            var gen = kw * cfg.unitsPerKw;
            var monthly = Math.min(gen, m) * cfg.tariff;
            var cost = kw * cfg.costPerKw, sub = subsidy(kw), net = cost - sub;
            return {
                units: m, kw: kw, generation: gen, monthly_saving: monthly,
                yearly_saving: monthly * 12, cost: cost, subsidy: sub, net_cost: net,
                payback_years: monthly ? (net / (monthly * 12)).toFixed(1) : 0,
                roof_sqft: kw * cfg.roofPerKw, bill: b || m * cfg.tariff,
            };
        }

        function render() {
            var e = compute();
            $("sp_result_empty").classList.toggle("d-none", !!e);
            $("sp_result_body").classList.toggle("d-none", !e);
            if (!e) { return; }
            document.querySelectorAll("[data-sp]").forEach(function (el) {
                var k = el.dataset.sp, v = e[k];
                if (v === undefined) { return; }
                el.textContent = (k === "kw" || k === "payback_years") ? v : fmt(v);
            });
            $("sp_hidden_kw").value = e.kw;
            $("sp_hidden_bill").value = Math.round(e.bill);
            $("sp_hidden_notes").value = "Website estimate: " + Math.round(e.units) +
                " units/month -> " + e.kw + " kW On-Grid";
        }

        units.addEventListener("input", function () { if (units.value) { bill.value = ""; } render(); });
        bill.addEventListener("input", function () { if (bill.value) { units.value = ""; } render(); });
        $("sp_usage_form").addEventListener("submit", function (ev) { ev.preventDefault(); render(); });

        // ---- Optional AI bill parsing (falls back to manual entry on any failure)
        var status = $("sp_bill_status");
        $("sp_bill_parse").addEventListener("click", function () {
            var f = $("sp_bill_file").files[0];
            if (!f) { status.textContent = "Choose a photo or PDF of your bill first."; return; }
            var fd = new FormData();
            fd.append("file", f);
            var ctrl = new AbortController();
            var timer = setTimeout(function () { ctrl.abort(); }, 65000);
            status.textContent = "Reading your bill… this can take up to a minute.";
            fetch(aiUrl + "/bill/parse", { method: "POST", body: fd, signal: ctrl.signal })
                .then(function (r) { return r.json().catch(function () { return {}; }); })
                .then(function (data) {
                    if (!data || data.ok !== true) { throw new Error("parse failed"); }
                    if (data.monthly_units_kwh) {
                        units.value = Math.round(data.monthly_units_kwh); bill.value = "";
                    } else if (data.bill_amount) {
                        bill.value = Math.round(data.bill_amount); units.value = "";
                    } else { throw new Error("no usage in bill"); }
                    status.textContent = "✔ Filled in from your bill" +
                        (data.discom ? " (" + data.discom + ")" : "") + ". Please check the numbers.";
                    render();
                })
                .catch(function () {
                    status.textContent = "We couldn't read the bill automatically. " +
                        "Please type your monthly units or bill amount above.";
                    units.focus();
                })
                .finally(function () { clearTimeout(timer); });
        });

        render();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

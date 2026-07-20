// init.js — Pre-fetch init data for instant dashboard rendering (fire and forget)
(function() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/init", true);
    xhr.timeout = 15000;
    xhr.onload = function() {
        if (xhr.status === 200) {
            try { window.__REST_INIT = JSON.parse(xhr.responseText); }
            catch(e) { console.warn("[INIT] parse error:", e); }
        } else {
            console.warn("[INIT] HTTP", xhr.status, xhr.statusText);
        }
    };
    xhr.onerror = function() { console.warn("[INIT] network error"); };
    xhr.ontimeout = function() { console.warn("[INIT] request timed out"); };
    xhr.onabort = function() {};
    xhr.send();
})();

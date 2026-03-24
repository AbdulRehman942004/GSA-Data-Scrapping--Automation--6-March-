"""
Creates a temporary Chrome extension for proxy authentication.

Selenium's Chrome WebDriver doesn't natively support authenticated proxies
(user:pass@host:port). This module generates a minimal Chrome extension
that intercepts the proxy auth challenge and supplies credentials.
"""
import os
import tempfile
import zipfile


def create_proxy_auth_extension(host: str, port: int, user: str, password: str) -> str:
    """Create a Chrome extension .zip that handles proxy auth.

    Returns the path to the temporary .zip file.
    The caller is responsible for cleanup (or let the OS handle it on exit).
    """
    manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Proxy Auth",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    }
}"""

    background_js = """var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: {
            scheme: "http",
            host: "%s",
            port: parseInt(%s)
        },
        bypassList: ["localhost"]
    }
};

chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

function callbackFn(details) {
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {urls: ["<all_urls>"]},
    ['blocking']
);""" % (host, port, user, password)

    # Write to a temp .zip file
    fd, path = tempfile.mkstemp(suffix=".zip", prefix="proxy_auth_")
    os.close(fd)

    with zipfile.ZipFile(path, "w") as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return path

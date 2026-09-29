[app]

title = Shoonya Bot
package.name = shoonyabot
package.domain = org.shoonya

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,json,xlsx,yml,yaml,css,js,html,bin
source.exclude_exts = spec,pyc
source.exclude_dirs = tests,bin,.buildozer

version = 0.1.0
orientation = portrait
fullscreen = 0

requirements = python3,kivy,flask,flask-socketio,simple-websocket,python-socketio,python-engineio,bidict,requests,charset_normalizer,websocket-client,pyyaml,pyotp,openpyxl,et_xmlfile,NorenRestApiPy

# (core) arm64-only to keep the build small and fast
android.archs = arm64-v8a

android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED,POST_NOTIFICATIONS
services = myservice:myservice/main.py:foreground:sticky
android.accept_sdk_license = True

[buildozer]

log_level = 2
warn_on_root = 0
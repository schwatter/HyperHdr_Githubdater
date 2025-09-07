## HyperHdr_Githubdater

Small script to scan, download and install HyperHdr from workflows in actions.
Written in python 2.7 for vu+ enigma2 and similar

This script only works with github-token.
1. Open https://github.com/settings/profile
2. Left down to developer settings
3. Personal access tokens
4. On the right open dropdown and hit "Generate new token (classic)"
5. Enter your password
6. Hit the workflow
7. Go down and enter "Generate token"
8. Save token in script @ TOKEN = "ghp_............."

The intern workdir is /tmp, so that the script can rest for example in persistent /home.
Start the script with
```
root@vuultimo4k:/# cd /home
root@vuultimo4k:/home# python HyperHdr_Githubdater.py
```

If you have HyperionNG installed, use this updater:
https://github.com/schwatter/HyperionNG_Githubdater

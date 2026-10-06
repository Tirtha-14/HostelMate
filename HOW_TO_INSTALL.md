# HostelMate UI update: install steps

This pack replaces ONLY your front end (HTML templates + CSS).
It does not touch app.py, db.py, matching.py, hostelmate.db or .secret_key,
so all your accounts, students and allocations stay exactly as they are.

## 1. Back up (30 seconds)
Copy your whole `hostelmate/` project folder somewhere safe (e.g. `hostelmate_backup/`).

## 2. Where the files go
Your project should end up looking like this:

```
hostelmate/
├── app.py              <- unchanged
├── db.py               <- unchanged
├── matching.py         <- unchanged
├── hostelmate.db       <- unchanged (your data)
├── .secret_key         <- unchanged
├── requirements.txt    <- unchanged
├── static/
│   └── style.css       <- REPLACE with static/style.css from this pack
└── templates/          <- REPLACE every file with the ones from this pack
    ├── base.html
    ├── auth_base.html      (new)
    ├── _flash.html         (new)
    ├── _macros.html
    ├── _prefs.html
    ├── error.html
    ├── login.html
    ├── student_register.html
    ├── admin_register.html
    ├── index.html
    ├── register.html
    ├── profile.html
    ├── students.html
    ├── student_view_profile.html
    ├── admin_home.html
    ├── admin_student_profile.html
    └── allocate.html
```

Steps:
1. Open your `hostelmate/templates/` folder and delete the old `.html` files inside it.
2. Copy ALL 17 `.html` files from this pack's `templates/` folder into it.
   (`auth_base.html` and `_flash.html` are new, so don't skip them.)
3. Copy this pack's `static/style.css` into `hostelmate/static/`, overwriting the old one.

## 3. Run
```bash
cd hostelmate
python app.py
```
Open http://127.0.0.1:5000 and press Ctrl + Shift + R (hard refresh) so the browser loads the new CSS.

## Troubleshooting
- Page looks unstyled / old: hard refresh (Ctrl + Shift + R).
- "Internal Server Error": the terminal prints the exact cause. Almost always a template file is missing from `templates/`. Check all 17 are there.
- Font looks different offline: the design uses the "Plus Jakarta Sans" Google Font. Without internet it falls back to Segoe UI automatically. Everything still works.

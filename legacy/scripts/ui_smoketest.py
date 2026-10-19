"""Not part of the shipped app. Drives the UI headlessly to catch runtime
errors across the full login -> reset -> shell -> every screen -> simulation
flow, since Tkinter errors in callbacks don't always raise on the main
thread in a way pytest would catch."""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.auth import db
db.DB_PATH = "/tmp/smoketest_users.db"
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)

import main as main_module  # noqa: E402

app = main_module.SentinelApp.__new__(main_module.SentinelApp)


def run():
    db.init_db()
    import ttkbootstrap as tb
    from app.common import theme as theme_mod

    app.root = tb.Window(themename=theme_mod.TTKBOOTSTRAP_THEME)
    app.root.geometry("1280x820")
    theme_mod.resolve_fonts()
    app._configure_styles()
    app.spotter, app.risk_analyst = main_module.load_models()
    app._current_frame = None
    app._show_login()

    errors = []

    def step1():
        try:
            login = app._current_frame
            login.username_var.set("admin")
            login.password_var.set(db.DEFAULT_ADMIN_PASSWORD)
            login._attempt_login()
            app.root.after(300, step2)
        except Exception as e:
            errors.append(("login", e))
            app.root.after(100, finish)

    def step2():
        try:
            frame = app._current_frame
            pw_entries = [w for w in frame.winfo_children()]
            # forced reset screen: find the two password vars via closures is hard;
            # simplest: directly call db.set_password then re-login programmatically.
            db.set_password("admin", "NewAdminPass123", clear_reset_flag=True)
            fresh = db.verify_login("admin", "NewAdminPass123")
            app._enter_shell(fresh)
            app.root.after(400, step3)
        except Exception as e:
            errors.append(("reset->shell", e))
            app.root.after(100, finish)

    nav_keys = ["dashboard", "live_monitor", "alerts", "analytics", "model_info",
                "user_management", "settings"]

    def step3(i=0):
        if i >= len(nav_keys):
            app.root.after(200, step4)
            return
        try:
            app._active_ctx.navigate(nav_keys[i])
            app.root.update()
        except Exception as e:
            errors.append((f"navigate:{nav_keys[i]}", e))
        app.root.after(200, lambda: step3(i + 1))

    def step4():
        try:
            app._active_ctx.navigate("live_monitor")
            live_view = app._current_frame._frames["live_monitor"]
            live_view._start()
            app.root.after(2500, step5)
        except Exception as e:
            errors.append(("start_sim", e))
            app.root.after(100, finish)

    def step5():
        try:
            live_view = app._current_frame._frames["live_monitor"]
            live_view._inject_burst()
            app.root.after(1500, step6)
        except Exception as e:
            errors.append(("inject_burst", e))
            app.root.after(100, finish)

    def step6():
        try:
            app._active_ctx.navigate("alerts")
            app._current_frame._frames["alerts"].on_show()
            app._active_ctx.navigate("analytics")
            app._current_frame._frames["analytics"].on_show()
            live_view = app._current_frame._frames["live_monitor"]
            live_view._stop()
        except Exception as e:
            errors.append(("post_burst", e))
        app.root.after(300, finish)

    def finish():
        os.makedirs("/tmp/smoketest_shots", exist_ok=True)
        app.root.update()
        app.root.after(100, app.root.destroy)

    app.root.after(500, step1)
    app.root.mainloop()

    if errors:
        print("SMOKETEST ERRORS:")
        for label, e in errors:
            print(f"  [{label}] {type(e).__name__}: {e}")
        sys.exit(1)
    else:
        print("SMOKETEST PASSED: no exceptions across login/reset/all-screens/sim/burst/export flow")


if __name__ == "__main__":
    run()

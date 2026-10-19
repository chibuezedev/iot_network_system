"""Users -- administrator-only user management (same SQLite users table and
db functions as before: create, edit role/active/forced reset, set password)."""
from __future__ import annotations

import sqlite3

import customtkinter as ctk

from app.auth import db
from app.screens.base import Screen
from app.ui import theme, tokens as T
from app.ui.widgets import Card, button, label, section_title, show_toast

ROLES = ["analyst", "administrator"]


def entry(parent, show: str = "", width: int = 200) -> ctk.CTkEntry:
    return ctk.CTkEntry(parent, width=width, height=34, show=show, font=theme.font("body"),
                        fg_color=T.SURFACE_2, border_color=T.BORDER, text_color=T.TEXT)


def option(parent, values, width: int = 150) -> ctk.CTkOptionMenu:
    m = ctk.CTkOptionMenu(parent, values=values, width=width, font=theme.font("small"),
                          dropdown_font=theme.font("small"), fg_color=T.SURFACE_2, button_color=T.SURFACE_2,
                          button_hover_color=T.BORDER, text_color=T.TEXT, dropdown_fg_color=T.SURFACE,
                          dropdown_text_color=T.TEXT, dropdown_hover_color=T.SURFACE_2)
    m.set(values[0])
    return m


class UsersScreen(Screen):
    title = "Users"
    subtitle = "Administrator access only. New accounts must set their own password at first sign-in."

    def build(self) -> None:
        self.header()
        self.selected_user_id: int | None = None
        if not self.ctx.is_admin():
            self.unavailable("Administrator access only.")
            return

        c = Card(self.page)
        self.section(c)
        section_title(c.body, "Create a user").pack(fill="x", pady=(0, 8))
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x")
        for i, cap in enumerate(("USERNAME", "TEMPORARY PASSWORD", "ROLE")):
            label(row, cap, "small_bold", T.MUTED).grid(row=0, column=i, sticky="w", padx=(0, 12))
        self.new_user = entry(row)
        self.new_user.grid(row=1, column=0, padx=(0, 12))
        self.new_pw = entry(row, show="•")
        self.new_pw.grid(row=1, column=1, padx=(0, 12))
        self.new_role = option(row, ROLES)
        self.new_role.grid(row=1, column=2, padx=(0, 12))
        button(row, "Add user", self._add_user, "primary", width=110).grid(row=1, column=3)

        lst = Card(self.page)
        self.section(lst)
        section_title(lst.body, "Accounts", "click a row to edit").pack(fill="x", pady=(0, 8))
        self.list = ctk.CTkFrame(lst.body, fg_color="transparent")
        self.list.pack(fill="x")

        ed = Card(self.page)
        self.section(ed)
        section_title(ed.body, "Selected user").pack(fill="x", pady=(0, 8))
        g = ctk.CTkFrame(ed.body, fg_color="transparent")
        g.pack(fill="x")
        for i, cap in enumerate(("USERNAME", "ROLE", "NEW PASSWORD (optional)", "CREATED")):
            label(g, cap, "small_bold", T.MUTED).grid(row=0, column=i, sticky="w", padx=(0, 12))
        self.e_user = entry(g)
        self.e_user.grid(row=1, column=0, padx=(0, 12))
        self.e_role = option(g, ROLES)
        self.e_role.grid(row=1, column=1, padx=(0, 12))
        self.e_pw = entry(g, show="•")
        self.e_pw.grid(row=1, column=2, padx=(0, 12))
        self.e_created = label(g, "No user selected", "mono", T.MUTED)
        self.e_created.grid(row=1, column=3, sticky="w")
        flags = ctk.CTkFrame(ed.body, fg_color="transparent")
        flags.pack(anchor="w", pady=(12, 0))
        self.e_active = ctk.CTkCheckBox(flags, text="Active", font=theme.font("body"), text_color=T.TEXT,
                                        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, border_color=T.BORDER)
        self.e_active.pack(side="left", padx=(0, 20))
        self.e_reset = ctk.CTkCheckBox(flags, text="Force password reset at next sign-in", font=theme.font("body"),
                                       text_color=T.TEXT, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                                       border_color=T.BORDER)
        self.e_reset.pack(side="left")
        acts = ctk.CTkFrame(ed.body, fg_color="transparent")
        acts.pack(anchor="w", pady=(14, 0))
        button(acts, "Save changes", self._save, "primary", width=140).pack(side="left")
        button(acts, "Clear selection", self._clear_editor, "secondary", width=140).pack(side="left", padx=8)

    def on_show(self) -> None:
        if self.ctx.is_admin():
            self._reload()

    # ------------------------------------------------------------------
    def _reload(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        heads = ("Username", "Role", "Created (UTC)", "Must reset password", "Active")
        for j, h in enumerate(heads):
            label(self.list, h, "small_bold", T.MUTED).grid(row=0, column=j, sticky="w", padx=10, pady=(0, 4))
        users = {u["id"]: u for u in db.list_users()}
        for i, u in enumerate(users.values(), start=1):
            sel = u["id"] == self.selected_user_id
            vals = (u["username"], u["role"], u["created_at"][:19].replace("T", " "),
                    "Yes" if u["must_reset_password"] else "No", "Yes" if u["active"] else "No")
            for j, v in enumerate(vals):
                lbl = label(self.list, v, "mono" if j == 2 else ("body_bold" if sel else "body"),
                            T.ACCENT if sel else (T.TEXT if u["active"] else T.MUTED), cursor="hand2")
                lbl.grid(row=i, column=j, sticky="w", padx=10, pady=3)
                lbl.bind("<Button-1>", lambda e, uid=u["id"]: self._select(uid))
        for j in range(len(heads)):
            self.list.columnconfigure(j, weight=1)
        if self.selected_user_id in users:
            self._populate(users[self.selected_user_id])
        else:
            self._clear_editor(reload=False)

    def _select(self, uid: int) -> None:
        self.selected_user_id = uid
        self._reload()

    def _populate(self, row) -> None:
        self.e_user.delete(0, "end")
        self.e_user.insert(0, row["username"])
        self.e_role.set(row["role"])
        (self.e_active.select if row["active"] else self.e_active.deselect)()
        (self.e_reset.select if row["must_reset_password"] else self.e_reset.deselect)()
        self.e_pw.delete(0, "end")
        self.e_created.configure(text=row["created_at"][:19].replace("T", " "))

    def _clear_editor(self, reload: bool = True) -> None:
        self.selected_user_id = None
        self.e_user.delete(0, "end")
        self.e_role.set("analyst")
        self.e_active.select()
        self.e_reset.deselect()
        self.e_pw.delete(0, "end")
        self.e_created.configure(text="No user selected")
        if reload:
            self._reload()

    def _add_user(self) -> None:
        username, password, role = self.new_user.get().strip(), self.new_pw.get(), self.new_role.get()
        if not username or not password:
            show_toast(self, "Missing fields", "Username and password are required.", "warning")
            return
        try:
            db.create_user(username, password, role)
        except sqlite3.IntegrityError:
            show_toast(self, "Could not add user", f"Username '{username}' already exists.", "critical")
            return
        except Exception as exc:
            show_toast(self, "Could not add user", str(exc), "critical")
            return
        self.new_user.delete(0, "end")
        self.new_pw.delete(0, "end")
        self._reload()
        show_toast(self, "User added", f"{username} created with role '{role}'.", "success")

    def _save(self) -> None:
        if self.selected_user_id is None:
            show_toast(self, "No user selected", "Choose a user from the list before saving changes.", "warning")
            return
        username = self.e_user.get().strip()
        if not username:
            show_toast(self, "Missing fields", "Username cannot be empty.", "warning")
            return
        try:
            db.update_user(self.selected_user_id, username=username, role=self.e_role.get(),
                           active=bool(self.e_active.get()), must_reset_password=bool(self.e_reset.get()),
                           new_password=self.e_pw.get() or None)
        except sqlite3.IntegrityError:
            show_toast(self, "Could not update user", f"Username '{username}' already exists.", "critical")
            return
        except Exception as exc:
            show_toast(self, "Could not update user", str(exc), "critical")
            return
        self._reload()
        show_toast(self, "User updated", f"{username} changes saved.", "success")

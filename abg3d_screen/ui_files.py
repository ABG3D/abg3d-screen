"""Files: browse G-code from Moonraker `server/files/list`, lazy thumbnails + metadata, start prints."""
import posixpath
import time
from collections import OrderedDict

from gi.repository import GLib, Gtk

from .core import Panel
from .icons import Icon
from .widgets import HBox, IconBtn, Lbl, Scroller, VBox, add_cls, fmt_len, fmt_time, set_btn

EXTS = (".gcode", ".g", ".gco", ".ufp")


class FilesPanel(Panel):
    title = "Files"

    def __init__(self, app):
        super().__init__(app)
        self.path = ""
        self.files = []
        self.loaded = False
        self.gen = 0
        self.meta = OrderedDict()
        self._meta_queue = []
        self._meta_busy = False
        self._dirty_src = None
        self.thumb = app.ui.thumb_list
        self.up_btn = IconBtn("folder_up", None, self._up)
        self.path_lbl = Lbl("/", "title", ellipsize=True)
        self.sort_btn = IconBtn("sort", "Newest" if not app.ui.small else None, self._toggle_sort)
        top = HBox(self.up_btn, self.path_lbl, self.sort_btn, IconBtn("refresh", None, self.load), expand=(1,))
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", self._activated)
        self.status = Lbl("", "muted", xalign=0.5)
        self.status.set_no_show_all(True)
        self.widget = VBox(top, self.status, Scroller(self.listbox), expand=(2,))
        add_cls(self.widget, "panel")
        self._sort_label()
        self.mr.on("filelist_changed", self._on_changed)

    # ------------------------------------------------------------ loading
    def on_show(self):
        if not self.loaded:
            self.load()

    def on_ready(self):
        self.loaded = False
        if self.visible():
            self.load()

    def _on_changed(self, _info):
        self.loaded = False
        if self.visible() and not self._dirty_src:
            def go():
                self._dirty_src = None
                self.load()
                return False
            self._dirty_src = GLib.timeout_add(800, go)

    def _toggle_sort(self):
        s = self.app.settings
        s["files_sort"] = "name" if s.get("files_sort") == "date" else "date"
        self.app.save_settings()
        self._sort_label()
        self.render()

    def _sort_label(self):
        set_btn(self.sort_btn, label="A–Z" if self.app.settings.get("files_sort") == "name" else "Newest")

    def _up(self):
        if self.path:
            self.path = posixpath.dirname(self.path)
            self.render()

    def load(self):
        self._show_status("Loading…")
        self.mr.call("server.files.list", {"root": "gcodes"}, self._loaded)

    def _loaded(self, res, err):
        if err or res is None:
            self._show_status("Error: %s" % (err or {}).get("message", "no response"))
            return
        self.loaded = True
        self.files = [f for f in res if isinstance(f, dict) and f.get("path", "").lower().endswith(EXTS)
                      and not any(p.startswith(".") for p in f["path"].split("/"))]
        self.render()

    def _show_status(self, text):
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    # ------------------------------------------------------------ rendering
    def _entries(self):
        prefix = self.path + "/" if self.path else ""
        dirs, files = {}, []
        for f in self.files:
            p = f["path"]
            if not p.startswith(prefix):
                continue
            rest = p[len(prefix):]
            if "/" in rest:
                d = rest.split("/", 1)[0]
                dirs[d] = max(dirs.get(d, 0), f.get("modified", 0))
            else:
                files.append(f)
        by_name = self.app.settings.get("files_sort") == "name"
        dl = sorted(dirs.items(), key=(lambda d: d[0].lower()) if by_name else (lambda d: -d[1]))
        files.sort(key=(lambda f: f["path"].lower()) if by_name else (lambda f: -f.get("modified", 0)))
        return dl, files

    def render(self):
        self.gen += 1
        self._meta_queue = []
        for c in self.listbox.get_children():
            self.listbox.remove(c)
            c.destroy()
        self.path_lbl.set_text("/" + self.path)
        dirs, files = self._entries()
        for name, _mod in dirs:
            self._row_dir(name)
        for f in files:
            self._row_file(f)
        self._show_status("" if dirs or files else "No G-code files")
        self.listbox.show_all()
        self._pump_meta()

    def _row_dir(self, name):
        ic = Icon("folder", self.thumb - 8)
        ic.set_size_request(self.thumb, self.thumb)
        row = Gtk.ListBoxRow()
        row.add(HBox(ic, VBox(Lbl(name, "title", ellipsize=True), Lbl("Folder", "muted", "small"), spacing=0),
                     expand=(1,)))
        row.kind, row.name = "dir", name
        add_cls(row, "filerow")
        self.listbox.add(row)

    def _row_file(self, f):
        path = f["path"]
        img = Gtk.Image()
        img.set_size_request(self.thumb, self.thumb)
        add_cls(img, "thumb")
        sub = Lbl(self._sub_text(f, self.meta.get(path)), "muted", "small", ellipsize=True)
        row = Gtk.ListBoxRow()
        row.add(HBox(img, VBox(Lbl(posixpath.basename(path), "title", ellipsize=True), sub, spacing=0),
                     expand=(1,)))
        row.kind, row.path, row.entry = "file", path, f
        add_cls(row, "filerow")
        self.listbox.add(row)
        m = self.meta.get(path)
        if m is not None and m.get("_mod") == f.get("modified"):
            self._apply_meta(path, m, img, sub, self.gen)
        else:
            self._meta_queue.append((path, f, img, sub))

    @staticmethod
    def _sub_text(f, m):
        bits = []
        if m:
            if m.get("estimated_time"):
                bits.append(fmt_time(m["estimated_time"]))
            if m.get("filament_total"):
                bits.append(fmt_len(m["filament_total"]))
            if m.get("filament_weight_total"):
                bits.append("%.0f g" % m["filament_weight_total"])
        if f.get("modified"):
            bits.append(time.strftime("%Y-%m-%d %H:%M", time.localtime(f["modified"])))
        return "  •  ".join(bits)

    def _pump_meta(self):
        """Fetch metadata one file at a time to keep RAM/CPU flat on large libraries."""
        if self._meta_busy or not self._meta_queue:
            return
        path, f, img, sub = self._meta_queue.pop(0)
        gen = self.gen
        self._meta_busy = True

        def done(res, err):
            self._meta_busy = False
            if res and not err:
                res["_mod"] = f.get("modified")
                self.meta[path] = res
                self.meta.move_to_end(path)
                while len(self.meta) > 400:
                    self.meta.popitem(last=False)
                if gen == self.gen:
                    self._apply_meta(path, res, img, sub, gen)
            if gen == self.gen:
                self._pump_meta()
        self.mr.call("server.files.metadata", {"filename": path}, done)

    def _apply_meta(self, path, m, img, sub, gen):
        entry = next((f for f in self.files if f["path"] == path), {})
        sub.set_text(self._sub_text(entry, m))
        if m.get("thumbnails"):
            self.app.thumbs.load(path, m["thumbnails"], self.thumb,
                                 lambda pb: pb and gen == self.gen and img.set_from_pixbuf(pb))

    def _activated(self, _lb, row):
        if row.kind == "dir":
            self.path = posixpath.join(self.path, row.name) if self.path else row.name
            self.render()
        else:
            self._details(row.path, self.meta.get(row.path) or {})

    # ------------------------------------------------------------- details
    def _details(self, path, meta):
        app = self.app
        ui = app.ui
        size = max(64, min(200, int(ui.h * 0.38)))
        img = Gtk.Image()
        img.set_size_request(size, size)
        add_cls(img, "thumb")
        if meta.get("thumbnails"):
            app.thumbs.load(path, meta["thumbnails"], size, lambda pb: pb and img.set_from_pixbuf(pb))
        info = []
        for label, key, fmt in (("Time", "estimated_time", fmt_time),
                                ("Filament", "filament_total", fmt_len),
                                ("Weight", "filament_weight_total", lambda v: "%.1f g" % v),
                                ("Layer", "layer_height", lambda v: "%.2f mm" % v),
                                ("Height", "object_height", lambda v: "%.1f mm" % v),
                                ("Material", "filament_type", str),
                                ("Slicer", "slicer", str)):
            if meta.get(key):
                try:
                    info.append("%s: %s" % (label, fmt(meta[key])))
                except (TypeError, ValueError):
                    pass
        text = VBox(Lbl(posixpath.basename(path), "title", wrap=True),
                    Lbl("\n".join(info) or "No metadata", "muted", "small"))
        text.set_size_request(int(ui.w * 0.32), -1)
        holder = {}

        def close():
            app.close_modal(holder["m"])

        def start():
            close()
            if self.mr.is_printing():
                app.toast("A print is already running", error=True)
                return
            self.mr.call("printer.print.start", {"filename": path},
                         lambda r, e: app.toast(e["message"], error=True) if e else app.show_panel("home"))

        def delete():
            close()
            app.confirm("Delete %s?" % posixpath.basename(path),
                        lambda: self.mr.call("server.files.delete_file", {"path": "gcodes/" + path},
                                             lambda r, e: e and app.toast(e["message"], error=True)),
                        ok="Delete", danger=True)
        lbl = not ui.small
        box = VBox(HBox(img, text, expand=(1,)),
                   HBox(IconBtn("trash", "Delete" if lbl else None, delete, "danger"),
                        IconBtn("close", "Close" if lbl else None, close),
                        IconBtn("play", "Print", start, "primary"), homogeneous=True))
        holder["m"] = app.show_modal(box)


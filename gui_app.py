import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ttkthemes import ThemedTk
import json
import os
import pandas as pd
import subprocess
import sys
import threading
import queue
import automation_script
import updater
from PIL import Image, ImageTk
import ctypes

try:
    myappid = 'sapo.partero.automation.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


def resource_path(relative_path):
    """Ruta a recursos empaquetados dentro del exe (sys._MEIPASS)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def app_dir():
    """Directorio donde vive el exe (o el script en desarrollo)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_plantilla():
    """Copia plantilla_partes.xlsx junto al exe si el usuario aún no la tiene."""
    dest = os.path.join(app_dir(), "plantilla_partes.xlsx")
    if not os.path.exists(dest):
        src = resource_path("plantilla_partes.xlsx")
        if os.path.exists(src):
            import shutil
            shutil.copy2(src, dest)


PROJECTS_FILE = os.path.join(app_dir(), "projects.xlsx")
CONFIG_FILE = os.path.join(app_dir(), "config.json")
ICON_FILE = resource_path("sapo_partero.ico")


class AutomationWizard:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Sapo partero  v{updater.VERSION}")
        self.root.geometry("700x600")

        if os.path.exists(ICON_FILE):
            try:
                self.root.iconbitmap(ICON_FILE)
            except Exception as e:
                print(f"Error cargando icono: {e}")

        style = ttk.Style()
        style.configure("TLabel", foreground="white", background="#464646")
        style.configure("TButton", foreground="white")
        style.configure("TLabelframe.Label", foreground="white", background="#464646")
        style.configure("TLabelframe", background="#464646")
        style.configure("Treeview.Heading", foreground="white")
        style.configure("Treeview", foreground="white")

        self.main_frame = ttk.Frame(root, padding="20")
        self.main_frame.pack(fill='both', expand=True)

        self.nav_frame = ttk.Frame(self.main_frame)
        self.nav_frame.pack(fill='x', pady=(0, 20))

        self.step_labels = []
        for step in ["1. Credenciales", "2. Proceso", "3. Ejecución"]:
            lbl = ttk.Label(self.nav_frame, text=step, font=('Segoe UI', 10, 'bold'), foreground='white')
            lbl.pack(side='left', padx=20)
            self.step_labels.append(lbl)

        try:
            img_path = resource_path("sapo_partero.png")
            if os.path.exists(img_path):
                pil_img = Image.open(img_path).resize((100, 100), Image.Resampling.NEAREST)
                self.sapo_icon = ImageTk.PhotoImage(pil_img)
                ttk.Label(self.nav_frame, image=self.sapo_icon).pack(side='right', padx=10)
        except Exception as e:
            print(f"Error loading sapo icon: {e}")

        # Process state
        self.selected_process = None   # 'normal' | 'bulk' | 'delete'
        self.bulk_file_path = None
        self.delete_desde_date = None
        self.delete_hasta_date = None

        self.frames = {}
        self.frames[0] = self._create_credentials_frame()
        self.frames[1] = self._create_process_frame()
        self.frames[2] = self._create_execution_frame()

        self.current_step = 0

        self.footer_frame = ttk.Frame(self.main_frame)
        self.footer_frame.pack(fill='x', side='bottom', pady=10)

        self.btn_prev = ttk.Button(self.footer_frame, text="< Anterior", command=self.prev_step, cursor="hand2")
        self.btn_prev.pack(side='left')
        self.btn_next = ttk.Button(self.footer_frame, text="Siguiente >", command=self.next_step, cursor="hand2")
        self.btn_next.pack(side='right')

        tk.Label(self.root, text="Autor: Beñat Arroyo",
                 font=("Segoe UI", 8), fg="gray", bg="#464646").place(relx=0.5, rely=1.0, anchor="s")

        self.show_step(0)
        self._buscar_actualizacion_en_segundo_plano()

    # ------------------------------------------------------------------ #
    #  Navigation                                                          #
    # ------------------------------------------------------------------ #

    def show_step(self, step_index):
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[step_index].pack(fill='both', expand=True)

        for i, lbl in enumerate(self.step_labels):
            if i == step_index:
                lbl.configure(foreground='black', font=('Segoe UI', 11, 'bold'))
            else:
                lbl.configure(foreground='gray', font=('Segoe UI', 10))

        self.btn_prev.configure(state='disabled' if step_index == 0 else 'normal')

        if step_index == 2:
            self.btn_next.configure(text="Finalizar", state='disabled')
            self._update_execution_frame()
        else:
            self.btn_next.configure(text="Siguiente >", state='normal', command=self.next_step)

    def next_step(self):
        if self.current_step == 0:
            self.save_credentials()
        elif self.current_step == 1:
            if not self._validate_process():
                return
        if self.current_step < 2:
            self.current_step += 1
            self.show_step(self.current_step)

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.show_step(self.current_step)

    # ------------------------------------------------------------------ #
    #  Actualizaciones                                                    #
    # ------------------------------------------------------------------ #

    def _buscar_actualizacion_en_segundo_plano(self):
        """Comprueba si hay versión nueva sin bloquear la ventana."""
        def run():
            info = updater.comprobar_actualizacion(log=lambda m: None)
            if info:
                # Volvemos al hilo de tkinter para tocar la interfaz
                self.root.after(0, lambda: self._dialogo_actualizacion(info))

        threading.Thread(target=run, daemon=True).start()

    def buscar_actualizacion_manual(self):
        """Comprobación lanzada por el usuario: aquí sí informamos si no hay nada."""
        if not updater.esta_configurado():
            messagebox.showinfo(
                "Actualizaciones",
                "Todavía no se ha configurado el repositorio de GitHub.\n"
                "Edita updater.py y pon el usuario del repositorio.")
            return
        if getattr(sys, 'frozen', False):
            messagebox.showinfo(
                "Actualizaciones",
                "Esta versión es un ejecutable: el código va empaquetado dentro "
                "y no se puede actualizar solo.\nDescarga la versión nueva a mano.")
            return

        mensajes = []
        info = updater.comprobar_actualizacion(log=mensajes.append)
        if info:
            self._dialogo_actualizacion(info)
        elif mensajes:
            messagebox.showwarning("Actualizaciones", "\n".join(mensajes))
        else:
            messagebox.showinfo(
                "Actualizaciones",
                f"Ya tienes la última versión (v{updater.VERSION}).")

    def _dialogo_actualizacion(self, info):
        dialog = tk.Toplevel(self.root)
        dialog.title("Hay una versión nueva")
        dialog.geometry("520x400")
        dialog.configure(bg="#464646")
        dialog.grab_set()

        d = ttk.Frame(dialog, padding=15)
        d.pack(fill='both', expand=True)

        ttk.Label(d, text=f"Versión {info.get('version')} disponible",
                  font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(d, text=f"Tienes la v{updater.VERSION}",
                  foreground='gray', font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 10))

        ttk.Label(d, text="Cambios:", font=('Segoe UI', 10, 'bold')).pack(anchor='w')

        txt = tk.Text(d, height=9, font=('Segoe UI', 9), wrap='word',
                      fg="white", bg="#1e1e1e", relief='flat')
        txt.pack(fill='both', expand=True, pady=(4, 10))
        txt.insert('1.0', updater.texto_cambios(info) or "(sin detalles)")
        txt.configure(state='disabled')

        estado = ttk.Label(d, text="", font=('Segoe UI', 9))
        estado.pack(anchor='w')

        btns = ttk.Frame(d)
        btns.pack(fill='x', pady=(8, 0))

        ttk.Button(btns, text="Ahora no", command=dialog.destroy,
                   cursor="hand2").pack(side='left')

        def actualizar():
            btn_upd.configure(state='disabled')
            estado.configure(text="Descargando...", foreground='#f0a500')
            dialog.update_idletasks()

            mensajes = []
            ok = updater.descargar_actualizacion(info, log=mensajes.append)
            detalle = "\n".join(mensajes)

            if ok:
                estado.configure(text="Actualizado.", foreground='#4caf50')
                messagebox.showinfo(
                    "Actualización instalada",
                    f"Sapo Partero se ha actualizado a la v{info.get('version')}.\n\n"
                    f"Cierra y vuelve a abrir la aplicación para usar la versión nueva.\n\n"
                    f"{detalle}", parent=dialog)
                dialog.destroy()
            else:
                estado.configure(text="No se pudo actualizar.", foreground='#f0a500')
                btn_upd.configure(state='normal')
                messagebox.showwarning(
                    "No se pudo actualizar",
                    f"La versión que tienes sigue intacta.\n\n{detalle}", parent=dialog)

        btn_upd = tk.Button(btns, text="⬇ Actualizar ahora", command=actualizar,
                            bg="#5a7ab5", fg="white", font=('Segoe UI', 10, 'bold'),
                            relief="raised", cursor="hand2")
        btn_upd.pack(side='right')

    # ------------------------------------------------------------------ #
    #  Step 1 – Credentials                                               #
    # ------------------------------------------------------------------ #

    def _create_credentials_frame(self):
        frame = ttk.Frame(self.main_frame)
        ttk.Label(frame, text="Datos de inicio de sesión", font=('Segoe UI', 14, 'bold')).pack(pady=(0, 20))

        grp_kelio = ttk.LabelFrame(frame, text="Acceso a Kelio", padding=15)
        grp_kelio.pack(fill='x', pady=10)
        ttk.Label(grp_kelio, text="Usuario:").grid(row=0, column=0, sticky='w', pady=5)
        self.kelio_user = ttk.Entry(grp_kelio, width=30)
        self.kelio_user.grid(row=0, column=1, pady=5, padx=10)
        ttk.Label(grp_kelio, text="Contraseña:").grid(row=1, column=0, sticky='w', pady=5)
        self.kelio_pass = ttk.Entry(grp_kelio, width=30, show="*")
        self.kelio_pass.grid(row=1, column=1, pady=5, padx=10)

        grp_jump = ttk.LabelFrame(frame, text="Acceso a JUMP", padding=15)
        grp_jump.pack(fill='x', pady=10)
        ttk.Label(grp_jump, text="Usuario:").grid(row=0, column=0, sticky='w', pady=5)
        self.jump_user = ttk.Entry(grp_jump, width=30)
        self.jump_user.grid(row=0, column=1, pady=5, padx=10)
        ttk.Label(grp_jump, text="Contraseña:").grid(row=1, column=0, sticky='w', pady=5)
        self.jump_pass = ttk.Entry(grp_jump, width=30, show="*")
        self.jump_pass.grid(row=1, column=1, pady=5, padx=10)

        pie = ttk.Frame(frame)
        pie.pack(fill='x', pady=(15, 0))
        ttk.Label(pie, text=f"Versión {updater.VERSION}",
                  foreground='gray', font=('Segoe UI', 9)).pack(side='left')
        ttk.Button(pie, text="Buscar actualizaciones",
                   command=self.buscar_actualizacion_manual,
                   cursor="hand2").pack(side='right')

        self.load_credentials()
        return frame

    def load_credentials(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.kelio_user.insert(0, data.get('kelio_user', ''))
                    self.kelio_pass.insert(0, data.get('kelio_password', ''))
                    self.jump_user.insert(0, data.get('jump_user', ''))
                    self.jump_pass.insert(0, data.get('jump_password', ''))
            except:
                pass

    def save_credentials(self):
        with open(CONFIG_FILE, 'w') as f:
            # .strip(): un espacio pegado al copiar y pegar hace fallar el login
            json.dump({
                'kelio_user': self.kelio_user.get().strip(),
                'kelio_password': self.kelio_pass.get().strip(),
                'jump_user': self.jump_user.get().strip(),
                'jump_password': self.jump_pass.get().strip()
            }, f)

    # ------------------------------------------------------------------ #
    #  Step 2 – Process selection                                         #
    # ------------------------------------------------------------------ #

    def _create_process_frame(self):
        frame = ttk.Frame(self.main_frame)
        ttk.Label(frame, text="¿Qué quieres hacer?", font=('Segoe UI', 14, 'bold')).pack(pady=(0, 15))

        self._process_var = tk.StringVar(value="")

        proc_defs = [
            ('normal', '▶  Automatización normal',
             'Lee horas de Kelio y crea partes en JUMP — requiere proyectos configurados'),
            ('bulk',   '📂  Carga masiva desde Excel',
             'Envía partes definidos en una plantilla Excel'),
            ('delete', '🗑  Borrado masivo',
             'Elimina todos los partes de un rango de fechas'),
        ]

        cards_frame = ttk.Frame(frame)
        cards_frame.pack(fill='x', padx=10)

        for key, title, desc in proc_defs:
            card = ttk.LabelFrame(cards_frame, padding=8)
            card.pack(fill='x', pady=4)
            ttk.Radiobutton(card, text=title, variable=self._process_var, value=key,
                            command=self._on_process_select, cursor='hand2').pack(anchor='w')
            ttk.Label(card, text=desc, foreground='gray',
                      font=('Segoe UI', 9)).pack(anchor='w', padx=22)

        # Sub-options (appear depending on selection)
        self._sub_opts = ttk.Frame(frame)
        self._sub_opts.pack(fill='x', padx=10, pady=(4, 0))

        # Normal: projects management + schedule info
        self._normal_sub = ttk.LabelFrame(self._sub_opts, text="Configuración de proyectos", padding=10)
        ttk.Label(self._normal_sub,
                  text="El programa reparte cada día al proyecto con más horas disponibles.\n"
                       "Es necesario tener al menos un proyecto configurado.",
                  font=('Segoe UI', 9), foreground='gray').pack(anchor='w', pady=(0, 6))
        self._proj_status_lbl = ttk.Label(self._normal_sub, text="", font=('Segoe UI', 9, 'bold'))
        self._proj_status_lbl.pack(anchor='w', pady=(0, 6))
        ttk.Button(self._normal_sub, text="📋 Gestión de Proyectos",
                   command=self._show_projects_dialog, cursor='hand2').pack(anchor='w')
        ttk.Label(self._normal_sub,
                  text="La tarea programada diaria (09:00) se configura en el siguiente paso.",
                  font=('Segoe UI', 9), foreground='gray').pack(anchor='w', pady=(8, 0))

        # Bulk: file picker
        self._bulk_sub = ttk.Frame(self._sub_opts)
        ttk.Label(self._bulk_sub, text="Archivo Excel:").pack(side='left')
        self._bulk_path_var = tk.StringVar()
        ttk.Entry(self._bulk_sub, textvariable=self._bulk_path_var,
                  width=36, state='readonly').pack(side='left', padx=5)
        ttk.Button(self._bulk_sub, text="Examinar…",
                   command=self._browse_bulk, cursor='hand2').pack(side='left')

        # Delete: date range
        self._delete_sub = ttk.Frame(self._sub_opts)
        ttk.Label(self._delete_sub, text="Desde (DD/MM/YYYY):").grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self._del_desde = ttk.Entry(self._delete_sub, width=14)
        self._del_desde.grid(row=0, column=1, padx=5)
        ttk.Label(self._delete_sub, text="Hasta (DD/MM/YYYY):").grid(row=1, column=0, sticky='w', padx=5, pady=3)
        self._del_hasta = ttk.Entry(self._delete_sub, width=14)
        self._del_hasta.grid(row=1, column=1, padx=5)

        return frame

    def _on_process_select(self):
        for w in self._sub_opts.winfo_children():
            w.pack_forget()
        proc = self._process_var.get()
        if proc == 'normal':
            self._update_proj_status()
            self._normal_sub.pack(fill='x', pady=6)
        elif proc == 'bulk':
            self._bulk_sub.pack(fill='x', pady=6)
        elif proc == 'delete':
            self._delete_sub.pack(fill='x', pady=6)

    def _update_proj_status(self):
        try:
            if not os.path.exists(PROJECTS_FILE):
                self._proj_status_lbl.configure(
                    text="⚠  Sin proyectos configurados. Añade al menos uno.",
                    foreground='#f0a500')
                return
            df = pd.read_excel(PROJECTS_FILE)
            for col in ['Total Hours', 'Executed Hours']:
                if col not in df.columns:
                    df[col] = 0
            df['_avail'] = pd.to_numeric(df['Total Hours'], errors='coerce').fillna(0) \
                         - pd.to_numeric(df['Executed Hours'], errors='coerce').fillna(0)
            n_total = len(df)
            n_active = int((df['_avail'] > 0).sum())
            if n_active > 0:
                self._proj_status_lbl.configure(
                    text=f"✔  {n_total} proyecto(s) — {n_active} con horas disponibles",
                    foreground='#4caf50')
            else:
                self._proj_status_lbl.configure(
                    text=f"⚠  {n_total} proyecto(s) pero ninguno con horas disponibles",
                    foreground='#f0a500')
        except Exception:
            self._proj_status_lbl.configure(
                text="No se pudo leer el Excel de proyectos.", foreground='gray')

    def _browse_bulk(self):
        path = filedialog.askopenfilename(
            title="Selecciona el Excel de partes",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if path:
            self._bulk_path_var.set(path)

    def _validate_process(self):
        proc = self._process_var.get()
        if not proc:
            messagebox.showwarning("Aviso", "Selecciona un proceso antes de continuar.")
            return False

        if proc == 'normal':
            if not os.path.exists(PROJECTS_FILE):
                messagebox.showerror(
                    "Sin proyectos",
                    "No hay proyectos configurados.\n"
                    "Abre 'Gestión de Proyectos' y añade al menos uno antes de continuar.")
                return False
            try:
                df_p = pd.read_excel(PROJECTS_FILE)
                avail = pd.to_numeric(df_p.get('Total Hours', 0), errors='coerce').fillna(0) \
                      - pd.to_numeric(df_p.get('Executed Hours', 0), errors='coerce').fillna(0)
                if (avail > 0).sum() == 0:
                    messagebox.showwarning(
                        "Sin horas disponibles",
                        "Todos los proyectos tienen las horas agotadas.\n"
                        "Añade o amplía proyectos en 'Gestión de Proyectos'.")
                    return False
            except Exception:
                pass  # Si no se puede leer, dejamos pasar (el script reportará el error)

        if proc == 'bulk':
            path = self._bulk_path_var.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showerror("Error", "Selecciona un archivo Excel válido.")
                return False
            try:
                df = pd.read_excel(path)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")
                return False
            missing = {'Fecha', 'Proyecto', 'Partida', 'Cantidad'} - set(df.columns)
            if missing:
                messagebox.showerror("Error", f"Faltan columnas en el Excel:\n{', '.join(missing)}")
                return False
            valid_rows = df[df['Fecha'].notna() & df['Proyecto'].notna()].copy()
            if valid_rows.empty:
                messagebox.showwarning("Aviso", "El Excel no contiene filas con datos válidos.")
                return False
            if not self._show_bulk_confirmation(path, valid_rows):
                return False
            self.bulk_file_path = path

        elif proc == 'delete':
            desde_str = self._del_desde.get().strip()
            hasta_str = self._del_hasta.get().strip()
            if not desde_str or not hasta_str:
                messagebox.showerror("Error", "Debes introducir ambas fechas (Desde y Hasta) antes de continuar.")
                return False
            try:
                desde = pd.to_datetime(desde_str, dayfirst=True).date()
                hasta = pd.to_datetime(hasta_str, dayfirst=True).date()
            except:
                messagebox.showerror("Error", "Formato de fecha inválido. Use DD/MM/YYYY.")
                return False
            if hasta < desde:
                messagebox.showerror("Error", "La fecha 'Hasta' debe ser igual o posterior a 'Desde'.")
                return False
            if not messagebox.askyesno("Confirmar borrado",
                    f"¿Seguro que quieres eliminar TODOS los partes\n"
                    f"entre el {desde_str} y el {hasta_str}?\n\n"
                    f"Esta acción no se puede deshacer.", icon='warning'):
                return False
            self.delete_desde_date = desde
            self.delete_hasta_date = hasta

        self.selected_process = proc
        return True

    # Confirmation dialog for bulk load — returns True if confirmed
    def _show_bulk_confirmation(self, excel_path, valid_rows):
        result = {'ok': False}

        dialog = tk.Toplevel(self.root)
        dialog.title("Confirmación de carga masiva")
        dialog.geometry("780x500")
        dialog.configure(bg="#464646")
        dialog.grab_set()

        d_frame = ttk.Frame(dialog, padding=15)
        d_frame.pack(fill='both', expand=True)

        ttk.Label(d_frame,
                  text="⚠  Se enviarán los siguientes partes de trabajo",
                  font=('Segoe UI', 11, 'bold'), foreground='#f0a500').pack(pady=(0, 4))
        ttk.Label(d_frame,
                  text=f"Total de partes a enviar: {len(valid_rows)}",
                  font=('Segoe UI', 10)).pack(pady=(0, 6))

        # Buttons packed FIRST so they're always visible
        btn_frame = ttk.Frame(d_frame)
        btn_frame.pack(side='bottom', fill='x', pady=(8, 0))

        ttk.Button(btn_frame, text="Cancelar",
                   command=dialog.destroy, cursor="hand2").pack(side='left', padx=5)

        def confirm():
            result['ok'] = True
            dialog.destroy()

        tk.Button(btn_frame, text="✔ Confirmar y enviar", command=confirm,
                  bg="#5a7ab5", fg="white", font=('Segoe UI', 10, 'bold'),
                  relief="raised", cursor="hand2").pack(side='right', padx=5)

        # Treeview fills the remaining space
        tree_frame = ttk.Frame(d_frame)
        tree_frame.pack(fill='both', expand=True)

        cols = ('Fecha', 'Proyecto', 'Partida', 'Horas', 'Modo')
        tree = ttk.Treeview(tree_frame, columns=cols, show='headings')
        tree.heading('Fecha', text='Fecha');     tree.column('Fecha', width=90)
        tree.heading('Proyecto', text='Proyecto'); tree.column('Proyecto', width=200)
        tree.heading('Partida', text='Partida');  tree.column('Partida', width=185)
        tree.heading('Horas', text='Horas');      tree.column('Horas', width=70)
        tree.heading('Modo', text='Modo');        tree.column('Modo', width=110)

        sb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree['yscrollcommand'] = sb.set
        sb.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)

        for _, row in valid_rows.iterrows():
            try:
                fecha_str = pd.to_datetime(row['Fecha'], dayfirst=True).strftime("%d/%m/%Y")
            except:
                fecha_str = str(row['Fecha'])
            h, m = self._parse_hm(row.get('Cantidad'), row.get('Cantidad2'))
            tree.insert('', 'end', values=(
                fecha_str,
                str(row.get('Proyecto', '')),
                str(row.get('Partida', '')),
                f"{h:02d}:{m:02d}",
                str(row.get('Modo de trabajo', 'Presencial'))
            ))

        dialog.wait_window()
        return result['ok']

    @staticmethod
    def _parse_hm(cantidad, cantidad2):
        h, m = 0, 0
        if pd.notna(cantidad) and str(cantidad).strip() not in ('', 'nan'):
            try:
                val = cantidad
                if hasattr(val, 'hour'):
                    h, m = val.hour, val.minute
                elif isinstance(val, float) and 0.0 < val < 1.0:
                    total_min = round(val * 24 * 60)
                    h, m = divmod(total_min, 60)
                else:
                    parts = str(val).strip().split(':')
                    h = int(parts[0])
                    m = int(parts[1]) if len(parts) > 1 else 0
            except:
                pass
        if h == 0 and m == 0 and pd.notna(cantidad2) and str(cantidad2).strip() not in ('', 'nan'):
            try:
                dec = float(cantidad2)
                h = int(dec)
                m = round((dec - h) * 60)
            except:
                pass
        return h, m

    # ------------------------------------------------------------------ #
    #  Projects dialog (accessible from step 2)                           #
    # ------------------------------------------------------------------ #

    def _show_projects_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Gestión de Proyectos")
        dialog.geometry("720x480")
        dialog.configure(bg="#464646")
        dialog.bind('<Destroy>', lambda _: self._update_proj_status())

        d_frame = ttk.Frame(dialog, padding=15)
        d_frame.pack(fill='both', expand=True)

        ttk.Label(d_frame, text="Gestión de Proyectos",
                  font=('Segoe UI', 14, 'bold')).pack(pady=(0, 10))

        columns = ('Proyecto', 'Partida', 'Horas Totales', 'Horas Ejecutadas', 'Disponible', 'Fecha límite')
        self.tree = ttk.Treeview(d_frame, columns=columns, show='headings', height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        self.tree.pack(expand=True, fill='both', pady=10)

        btn_frame = ttk.Frame(d_frame)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="Añadir Proyecto",
                   command=self.add_project_dialog, cursor="hand2").pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Borrar Seleccionado",
                   command=self.delete_project, cursor="hand2").pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Abrir Excel",
                   command=self.open_excel, cursor="hand2").pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Recargar Excel",
                   command=self.load_projects, cursor="hand2").pack(side='right', padx=5)

        self.load_projects()

    def load_projects(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not os.path.exists(PROJECTS_FILE):
            pd.DataFrame(columns=['Project Name', 'Partida', 'Total Hours',
                                  'Executed Hours', 'Available', 'Fecha límite']
                         ).to_excel(PROJECTS_FILE, index=False)
        try:
            df = pd.read_excel(PROJECTS_FILE)
            for col in ['Project Name', 'Partida', 'Total Hours', 'Executed Hours', 'Available', 'Fecha límite']:
                if col not in df.columns:
                    df[col] = None
            for col in ['Total Hours', 'Executed Hours', 'Available']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df['Available'] = df['Total Hours'] - df['Executed Hours']
            for _, row in df.iterrows():
                date_str = ""
                if pd.notna(row['Fecha límite']):
                    try:
                        date_str = pd.to_datetime(row['Fecha límite'], dayfirst=True).strftime("%d/%m/%Y")
                    except:
                        date_str = str(row['Fecha límite'])
                self.tree.insert('', 'end', values=(
                    row['Project Name'], row['Partida'],
                    row['Total Hours'], row['Executed Hours'],
                    f"{row['Available']:.2f}", date_str
                ))
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar proyectos: {e}")

    def open_excel(self):
        try:
            if os.path.exists(PROJECTS_FILE):
                os.startfile(PROJECTS_FILE)
            else:
                messagebox.showwarning("Aviso", "El archivo de proyectos no existe aún.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el Excel: {e}")

    def add_project_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Añadir Proyecto")
        dialog.geometry("400x380")
        dialog.configure(bg="#464646")
        d_frame = ttk.Frame(dialog, padding=20)
        d_frame.pack(fill='both', expand=True)

        ttk.Label(d_frame, text="Nombre del Proyecto:").pack(pady=5)
        e_name = ttk.Entry(d_frame, width=40); e_name.pack(pady=5)
        ttk.Label(d_frame, text="Partida:").pack(pady=5)
        e_partida = ttk.Entry(d_frame, width=40); e_partida.pack(pady=5)
        ttk.Label(d_frame, text="Horas Totales:").pack(pady=5)
        e_hours = ttk.Entry(d_frame, width=20); e_hours.pack(pady=5)
        ttk.Label(d_frame, text="Fecha límite (DD/MM/YYYY) [Opcional]:").pack(pady=5)
        e_date = ttk.Entry(d_frame, width=20); e_date.pack(pady=5)

        def save():
            try:
                name = e_name.get()
                if not name:
                    return
                partida = e_partida.get()
                hours = float(e_hours.get())
                date_str = e_date.get().strip()
                if date_str:
                    try:
                        formatted_date = pd.to_datetime(date_str, dayfirst=True).strftime("%d/%m/%Y")
                    except:
                        messagebox.showerror("Error", "Formato de fecha inválido. Use DD/MM/YYYY")
                        return
                else:
                    formatted_date = f"31/12/{pd.Timestamp.now().year}"
                df = pd.read_excel(PROJECTS_FILE)
                if 'Fecha límite' not in df.columns:
                    df['Fecha límite'] = None
                df = pd.concat([df, pd.DataFrame([{
                    'Project Name': name, 'Partida': partida,
                    'Total Hours': hours, 'Executed Hours': 0,
                    'Available': hours, 'Fecha límite': formatted_date
                }])], ignore_index=True)
                df.to_excel(PROJECTS_FILE, index=False)
                self.load_projects()
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Las horas deben ser un número.")

        ttk.Button(d_frame, text="Guardar", command=save, cursor="hand2").pack(pady=20)

    def delete_project(self):
        selected = self.tree.selection()
        if not selected:
            return
        name = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Confirmar", f"¿Borrar proyecto '{name}'?"):
            df = pd.read_excel(PROJECTS_FILE)
            df = df[df['Project Name'] != name]
            df.to_excel(PROJECTS_FILE, index=False)
            self.load_projects()

    # ------------------------------------------------------------------ #
    #  Step 3 – Execution                                                 #
    # ------------------------------------------------------------------ #

    def _create_execution_frame(self):
        frame = ttk.Frame(self.main_frame)

        title_row = ttk.Frame(frame)
        title_row.pack(fill='x', pady=(0, 10))
        self._exec_title = ttk.Label(title_row, text="", font=('Segoe UI', 14, 'bold'))
        self._exec_title.pack(side='left')
        ttk.Button(title_row, text="↩ Nuevo proceso",
                   command=self._reset_to_process_select, cursor='hand2').pack(side='right')

        ctrl = ttk.Frame(frame)
        ctrl.pack(fill='x', pady=5)

        # Normal
        self._exec_normal = ttk.Frame(ctrl)
        self.btn_run = tk.Button(
            self._exec_normal, text="▶ Salta, sapo!",
            command=self._start_normal,
            bg="#e0e0e0", fg="black", font=('Segoe UI', 10, 'bold'),
            relief="raised", cursor="hand2")
        self.btn_run.pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(self._exec_normal, text="📅 Crear Tarea Diaria (09:00)",
                   command=self.create_scheduled_task, cursor="hand2").pack(side='right', padx=5)

        # Bulk
        self._exec_bulk = ttk.Frame(ctrl)
        self._exec_bulk_info = ttk.Label(self._exec_bulk, text="", foreground='gray', font=('Segoe UI', 9))
        self._exec_bulk_info.pack(anchor='w', padx=5, pady=(0, 4))
        self.btn_bulk_run = tk.Button(
            self._exec_bulk, text="▶ Iniciar carga masiva",
            command=self._start_bulk,
            bg="#5a7ab5", fg="white", font=('Segoe UI', 10, 'bold'),
            relief="raised", cursor="hand2")
        self.btn_bulk_run.pack(fill='x', padx=5)

        # Delete
        self._exec_delete = ttk.Frame(ctrl)
        self._exec_delete_info = ttk.Label(self._exec_delete, text="", foreground='#f0a500', font=('Segoe UI', 9))
        self._exec_delete_info.pack(anchor='w', padx=5, pady=(0, 4))
        self.btn_delete_run = tk.Button(
            self._exec_delete, text="🗑 Eliminar partes",
            command=self._start_delete,
            bg="#b54a4a", fg="white", font=('Segoe UI', 10, 'bold'),
            relief="raised", cursor="hand2")
        self.btn_delete_run.pack(fill='x', padx=5)

        # Log
        ttk.Label(frame, text="Registro de Actividad:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(10, 4))

        log_frame = ttk.Frame(frame)
        log_frame.pack(fill='both', expand=True)
        self.log_text = tk.Text(log_frame, state='disabled', font=('Consolas', 9),
                                fg="white", bg="#1e1e1e", insertbackground="white",
                                wrap=tk.NONE)
        v_sb = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        h_sb = ttk.Scrollbar(log_frame, orient='horizontal', command=self.log_text.xview)
        self.log_text['yscrollcommand'] = v_sb.set
        self.log_text['xscrollcommand'] = h_sb.set
        v_sb.pack(side='right', fill='y')
        h_sb.pack(side='bottom', fill='x')
        self.log_text.pack(fill='both', expand=True)

        return frame

    def _update_execution_frame(self):
        for f in (self._exec_normal, self._exec_bulk, self._exec_delete):
            f.pack_forget()

        proc = self.selected_process
        if proc == 'normal':
            self._exec_title.configure(text="Automatización normal")
            self._exec_normal.pack(fill='x')
        elif proc == 'bulk':
            self._exec_title.configure(text="Carga masiva desde Excel")
            fname = os.path.basename(self.bulk_file_path) if self.bulk_file_path else ""
            self._exec_bulk_info.configure(text=f"Archivo: {fname}")
            self._exec_bulk.pack(fill='x')
        elif proc == 'delete':
            self._exec_title.configure(text="Borrado masivo")
            if self.delete_desde_date and self.delete_hasta_date:
                self._exec_delete_info.configure(
                    text=f"Rango: {self.delete_desde_date.strftime('%d/%m/%Y')} → "
                         f"{self.delete_hasta_date.strftime('%d/%m/%Y')}")
            self._exec_delete.pack(fill='x')

    def log_message(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', message + "\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')
        self.root.update_idletasks()

    def _lock_nav(self, locked):
        state = 'disabled' if locked else 'normal'
        self.btn_prev.configure(state=state)

    def _reset_to_process_select(self):
        self.selected_process = None
        self.bulk_file_path = None
        self.delete_desde_date = None
        self.delete_hasta_date = None
        self._process_var.set("")
        for w in self._sub_opts.winfo_children():
            w.pack_forget()
        self.current_step = 1
        self.show_step(1)

    # --- Normal automation ---

    def _start_normal(self):
        self.btn_run.configure(state='disabled')
        self._lock_nav(True)
        self.log_message("--- Ahí va el sapo... ---")
        self.log_queue = queue.Queue()

        def run():
            try:
                automation_script.main(log_callback=self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"Error fatal: {e}")
            finally:
                self.log_queue.put("DONE_NORMAL")

        threading.Thread(target=run, daemon=True).start()
        self._poll("DONE_NORMAL", self.btn_run,
                   ok_msg="El sapo ha hecho su trabajo, ahora tú haz el tuyo.\n\nPD: invítale a un café a Beñat, que se lo merece.",
                   ok_title="Finalizado",
                   warn_title="Finalizado con errores",
                   warn_msg="El sapo ha tropezado en algún salto.\nRevisa el registro de actividad.")

    # --- Bulk load ---

    def _start_bulk(self):
        self.btn_bulk_run.configure(state='disabled')
        self._lock_nav(True)
        self.log_message(f"--- Iniciando carga masiva: {os.path.basename(self.bulk_file_path)} ---")
        self.log_queue = queue.Queue()

        def run():
            try:
                automation_script.submit_bulk_from_excel(self.bulk_file_path, log_callback=self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"Error fatal: {e}")
            finally:
                self.log_queue.put("DONE_BULK")

        threading.Thread(target=run, daemon=True).start()
        self._poll("DONE_BULK", self.btn_bulk_run,
                   ok_msg="Todos los partes han sido procesados correctamente.",
                   ok_title="Carga masiva finalizada",
                   warn_title="Carga masiva con errores",
                   warn_msg="Algunos partes pueden no haberse enviado.\nRevisa el registro.")

    # --- Bulk delete ---

    def _start_delete(self):
        self.btn_delete_run.configure(state='disabled')
        self._lock_nav(True)
        self.log_message(
            f"--- Iniciando borrado masivo: "
            f"{self.delete_desde_date.strftime('%d/%m/%Y')} → "
            f"{self.delete_hasta_date.strftime('%d/%m/%Y')} ---")
        self.log_queue = queue.Queue()

        def run():
            try:
                automation_script.delete_bulk_partes(
                    self.delete_desde_date, self.delete_hasta_date,
                    log_callback=self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"Error fatal: {e}")
            finally:
                self.log_queue.put("DONE_DELETE")

        threading.Thread(target=run, daemon=True).start()
        self._poll("DONE_DELETE", self.btn_delete_run,
                   ok_msg="Los partes han sido eliminados correctamente.",
                   ok_title="Borrado finalizado",
                   warn_title="Borrado finalizado con avisos",
                   warn_msg="El proceso terminó pero puede haber ocurrido algún problema.\nRevisa el registro.")

    # Generic queue poller
    def _poll(self, sentinel, btn, ok_msg, ok_title, warn_title, warn_msg):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == sentinel:
                    btn.configure(state='normal')
                    self._lock_nav(False)
                    log = self.log_text.get("1.0", "end")
                    # Solo contar como error los prefijos explícitos del script
                    error_lines = [l for l in log.splitlines()
                                   if l.startswith("Error") or l.startswith("Fatal")
                                   or "No se han encontrado" in l or "⚠" in l]
                    if error_lines:
                        messagebox.showwarning(warn_title, warn_msg)
                    else:
                        messagebox.showinfo(ok_title, ok_msg)
                    return
                self.log_message(msg)
        except queue.Empty:
            pass
        self.root.after(100, lambda: self._poll(sentinel, btn, ok_msg, ok_title, warn_title, warn_msg))

    # ------------------------------------------------------------------ #
    #  Scheduled task                                                     #
    # ------------------------------------------------------------------ #

    def create_scheduled_task(self):
        try:
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
                exe_dir = os.path.dirname(app_path)
                argument = '--auto'
            else:
                # Ejecución desde fuente (p. ej. paquete portátil): usar pythonw.exe
                script_path = os.path.abspath(__file__)
                exe_dir = os.path.dirname(script_path)
                pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                app_path = pythonw if os.path.exists(pythonw) else sys.executable
                argument = f'"{script_path}" --auto'
            ps_cmd = (
                f"$action = New-ScheduledTaskAction -Execute '{app_path}' "
                f"-Argument '{argument}' -WorkingDirectory '{exe_dir}'; "
                f"$trigger = New-ScheduledTaskTrigger -Daily -At '09:00'; "
                f"Register-ScheduledTask -Action $action -Trigger $trigger "
                f"-TaskName 'Sapo_partero' "
                f"-Description 'Automatización de partes de trabajo' -Force"
            )
            subprocess.run(["powershell", "-Command", ps_cmd], check=True, capture_output=True, text=True)
            messagebox.showinfo("Éxito", "Tarea programada creada correctamente para las 09:00.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear la tarea: {e}")


if __name__ == "__main__":
    _ensure_plantilla()
    if "--auto" in sys.argv:
        automation_script.main()
        cmd = ("powershell -Command \"$w = New-Object -ComObject WScript.Shell; "
               "$w.Popup('El sapo ha terminado su ronda automática.', 60, 'Sapo Partero', 0)\"")
        subprocess.run(cmd, shell=True)
    else:
        root = ThemedTk(theme="equilux")
        app = AutomationWizard(root)
        root.mainloop()

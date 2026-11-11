"""Interface desktop para estimativa local da área projetada do antebraço."""
from __future__ import annotations

import argparse
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
from PIL import Image, ImageTk

from fisio_pipeline import ler_imagem
from fisio_servico import Servico, parametros, reduzir, exportar


class Aplicacao(tk.Tk):
    """Janela com análise em segundo plano e marcação manual de dois pontos."""
    def __init__(self, initial: Path | None = None) -> None:
        super().__init__()
        self.title('Fisio • Medição do antebraço')
        self.geometry('1220x820')
        self.minsize(1000, 720)
        self.configure(bg='#edf2f4')
        self.service = Servico()
        self.queue: Queue = Queue()
        self.path: Path | None = None
        self.original = None
        self.shown = None
        self.report = None
        self.overlays: list = []
        self.points: list[list[float]] = []
        self.marking = False
        self.busy = False
        self.preview = None
        self.mapping = (0., 0., 1., 1.)
        self.method = tk.StringVar(value='Círculo verde')
        self.size = tk.StringVar(value='19')
        self.slice = tk.StringVar(value='5')
        self.marker_id = tk.StringVar(value='0')
        self.side = tk.StringVar(value='não informado')
        self.selected = tk.StringVar()
        self.status = tk.StringVar(value='Comece selecionando uma foto com o marcador visível.')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton', padding=(12, 9), font=('Segoe UI', 10))
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('Accent.TButton', background='#087f83', foreground='white')
        header = tk.Frame(self, bg='#153e4a', padx=24, pady=18)
        header.pack(fill='x')
        tk.Label(header, text='Fisio / Medição do antebraço', bg='#153e4a', fg='white', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(header, text='Carregue a foto, confira o segmento e veja as áreas por fatia.', bg='#153e4a', fg='#c8e1e4', font=('Segoe UI', 11)).pack(anchor='w')
        toolbar = ttk.Frame(self, padding=12)
        toolbar.pack(fill='x')
        self.open_button = ttk.Button(toolbar, text='1. Abrir foto', command=self.open_photo)
        self.open_button.pack(side='left', padx=4)
        self.auto_button = ttk.Button(toolbar, text='2. Analisar automaticamente', style='Accent.TButton', command=self.analyze)
        self.auto_button.pack(side='left', padx=4)
        self.manual_button = ttk.Button(toolbar, text='Marcar cotovelo e punho', command=self.start_marking)
        self.manual_button.pack(side='left', padx=4)
        self.export_button = ttk.Button(toolbar, text='Exportar resultados', command=self.save)
        self.export_button.pack(side='right', padx=4)
        content = ttk.Panedwindow(self, orient='horizontal')
        content.pack(fill='both', expand=True, padx=16)
        left = ttk.Frame(content)
        right = ttk.Frame(content, padding=(16, 0), width=380)
        content.add(left, weight=3)
        content.add(right, weight=1)
        self.filename = ttk.Label(left, text='JPG, PNG ou HEIC • processamento no seu computador')
        self.filename.pack(anchor='w', pady=(0, 8))
        self.canvas = tk.Canvas(left, bg='#dce5e8', highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        self.canvas.bind('<Button-1>', self.click_photo)
        ttk.Button(left, text='Alternar original / resultado', command=self.toggle).pack(anchor='w', pady=8)
        ttk.Label(right, text='Configuração da medida', font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(0, 8))
        self.inputs = []
        for label, variable, choices in [('Marcador', self.method, ['Círculo verde', 'ArUco']), ('Tamanho real (mm)', self.size, None), ('Fatia (cm)', self.slice, None), ('ID ArUco (0–49)', self.marker_id, None), ('Lado no modo manual', self.side, ['não informado', 'esquerdo', 'direito'])]:
            row = ttk.Frame(right)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=label).pack(side='left')
            widget = ttk.Combobox(row, textvariable=variable, values=choices, state='readonly', width=18) if choices else ttk.Entry(row, textvariable=variable, width=12)
            widget.pack(side='right')
            self.inputs.append(widget)
        self.inputs[0].bind('<<ComboboxSelected>>', self.change_method)
        ttk.Label(right, text='Círculo: diâmetro. ArUco: lado do quadrado preto.\nAo alterar parâmetros, analise novamente.', wraplength=340).pack(anchor='w', pady=8)
        self.arm_combo = ttk.Combobox(right, textvariable=self.selected, state='readonly')
        self.arm_combo.pack(fill='x', pady=8)
        self.arm_combo.bind('<<ComboboxSelected>>', lambda _: self.show_arm())
        self.total = ttk.Label(right, text='— cm²', font=('Segoe UI', 26, 'bold'), foreground='#087f83')
        self.total.pack(anchor='w')
        ttk.Label(right, text='Área projetada estimada • revisão obrigatória').pack(anchor='w')
        self.table = ttk.Treeview(right, columns=('fatia', 'trecho', 'area'), show='headings', height=6)
        for key, label, width in [('fatia', 'Fatia', 50), ('trecho', 'Trecho (cm)', 130), ('area', 'Área (cm²)', 100)]:
            self.table.heading(key, text=label)
            self.table.column(key, width=width, stretch=True)
        self.table.pack(fill='x', pady=10)
        self.notes = tk.Text(right, height=7, width=35, wrap='word', font=('Segoe UI', 10), relief='flat', bg='#fff7e8')
        self.notes.pack(fill='both', expand=True)
        self.set_notes('Confira se a foto mostra punho e cotovelo, com foco e fundo uniforme. A tag verde padrão mede 19 mm.')
        self.progress = ttk.Progressbar(self, mode='indeterminate')
        self.progress.pack(fill='x', padx=16, pady=(8, 0))
        ttk.Label(self, textvariable=self.status, padding=(16, 8), wraplength=1150).pack(fill='x')
        ttk.Label(self, text='Esta estimativa 2D não representa volume nem superfície curva. A máscara precisa de conferência visual.', padding=(16, 5)).pack(fill='x')
        self.update_controls()
        self.after(100, self.poll)
        if initial:
            self.after(300, lambda: self.load(initial))

    def change_method(self, _=None) -> None:
        """Sugere dimensões padrão sem aplicar mudanças ao resultado anterior."""
        self.size.set('40' if self.method.get() == 'ArUco' else '19')
        self.status.set('Marcador alterado. Analise novamente para aplicar.')

    def set_notes(self, text: str) -> None:
        """Atualiza orientações em linguagem simples."""
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', text)
        self.notes.configure(state='disabled')

    def update_controls(self) -> None:
        """Bloqueia ações concorrentes e impede exportar resultados inexistentes."""
        self.open_button.configure(state='disabled' if self.busy else 'normal')
        for button in [self.auto_button, self.manual_button]:
            button.configure(state='normal' if self.path and not self.busy else 'disabled')
        self.export_button.configure(state='normal' if self.report and not self.busy else 'disabled')
        for widget in self.inputs:
            widget.configure(state='disabled' if self.busy else ('readonly' if isinstance(widget, ttk.Combobox) else 'normal'))

    def run_job(self, kind: str, function) -> None:
        """Executa trabalho pesado sem acessar Tk fora da thread principal."""
        self.busy = True
        self.update_controls()
        self.progress.start()
        def worker() -> None:
            try:
                self.queue.put((kind, function(), None))
            except Exception as exc:
                self.queue.put((kind, None, str(exc)))
        Thread(target=worker, daemon=True).start()

    def open_photo(self) -> None:
        """Seleciona arquivo local sem transmiti-lo a serviços externos."""
        path = filedialog.askopenfilename(title='Selecionar foto', filetypes=[('Fotos', '*.jpg *.jpeg *.png *.heic *.heif'), ('Todos os arquivos', '*.*')])
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        """Limpa dados anteriores antes de iniciar a leitura da próxima foto."""
        self.path = None
        self.report, self.overlays, self.points = None, [], []
        self.marking = False
        self.original = self.shown = None
        self.total.configure(text='— cm²')
        self.table.delete(*self.table.get_children())
        self.arm_combo['values'] = []
        self.selected.set('')
        self.filename.configure(text=path.name)
        self.set_notes('Carregando a nova foto. Confira o marcador e o tamanho físico antes da análise.')
        self.draw()
        self.status.set('Abrindo foto…')
        self.run_job('load', lambda: (path, reduzir(ler_imagem(path))))

    def analyze(self, manual: bool = False) -> None:
        """Captura parâmetros e inicia análise automática ou por pontos marcados."""
        if self.busy or not self.path:
            return
        try:
            args = parametros('aruco' if self.method.get() == 'ArUco' else 'circulo', float(self.size.get().replace(',', '.')), float(self.slice.get().replace(',', '.')), int(self.marker_id.get()))
        except ValueError as exc:
            messagebox.showerror('Confira os parâmetros', str(exc))
            return
        path, points, side = self.path, list(self.points) if manual else None, self.side.get()
        self.marking = False
        self.report = None
        self.overlays = []
        self.total.configure(text='— cm²')
        self.table.delete(*self.table.get_children())
        self.arm_combo['values'] = []
        self.selected.set('')
        self.status.set('Analisando… Na primeira análise, os modelos podem levar mais tempo para carregar.')
        self.run_job('analysis', lambda: self.service.analisar(path, args, points, side))

    def start_marking(self) -> None:
        """Inicia dois cliques ordenados: cotovelo e depois punho."""
        if self.busy or self.original is None:
            return
        self.points = []
        self.marking = True
        self.report = None
        self.overlays = []
        self.total.configure(text='— cm²')
        self.table.delete(*self.table.get_children())
        self.arm_combo['values'] = []
        self.selected.set('')
        self.update_controls()
        self.shown = self.original
        self.status.set('Clique no centro do COTOVELO. Depois clique no centro do PUNHO. A análise inicia após o segundo clique.')
        self.draw()

    def click_photo(self, event) -> None:
        """Converte clique da prévia para pixels processados com escalas independentes."""
        if not self.marking or self.busy:
            return
        ox, oy, sx, sy = self.mapping
        x, y = (event.x - ox) / sx, (event.y - oy) / sy
        if not (0 <= x < self.original.shape[1] and 0 <= y < self.original.shape[0]):
            return
        self.points.append([x, y])
        self.draw()
        if len(self.points) == 2:
            self.analyze(manual=True)
        else:
            self.status.set('Cotovelo marcado. Agora clique no centro do PUNHO.')

    def draw(self) -> None:
        """Ajusta a prévia à janela sem deformar a foto."""
        self.canvas.delete('all')
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.shown is None:
            self.canvas.create_text(width / 2, height / 2, text='Sua foto aparecerá aqui\n\nEscolha “Abrir foto” para começar.', justify='center', fill='#526b75', font=('Segoe UI', 14))
            return
        image = Image.fromarray(cv2.cvtColor(self.shown, cv2.COLOR_BGR2RGB))
        image.thumbnail((width, height))
        ox, oy = (width - image.width) / 2, (height - image.height) / 2
        sx, sy = image.width / self.shown.shape[1], image.height / self.shown.shape[0]
        self.mapping = (ox, oy, sx, sy)
        self.preview = ImageTk.PhotoImage(image)
        self.canvas.create_image(ox, oy, anchor='nw', image=self.preview)
        if self.marking:
            for i, (x, y) in enumerate(self.points):
                x, y = ox + x * sx, oy + y * sy
                self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill='#ffbf47', outline='white', width=2)
                self.canvas.create_text(x + 10, y - 12, anchor='w', text='Cotovelo' if i == 0 else 'Punho', fill='#153e4a', font=('Segoe UI', 11, 'bold'))

    def show_arm(self) -> None:
        """Mostra cada braço separadamente, sem somar áreas de lados diferentes."""
        i = self.arm_combo.current()
        if not self.report or i < 0:
            return
        arm = self.report['bracos'][i]
        self.shown = self.overlays[i]
        self.total.configure(text=f"{arm['area_total_cm2']:.2f} cm²".replace('.', ','))
        self.table.delete(*self.table.get_children())
        for s in arm['fatias']:
            self.table.insert('', 'end', values=(s['indice'], f"{s['inicio_cm']:.1f}–{s['fim_cm']:.1f}".replace('.', ','), f"{s['area_cm2']:.2f}".replace('.', ',')))
        self.set_notes('Revisão necessária: confira o contorno colorido e os limites do segmento. Use a marcação manual se punho ou cotovelo estiverem deslocados.\n\n' + self.quality_text(self.report['flags'] + arm['flags']))
        self.draw()

    @staticmethod
    def quality_text(flags: list[str]) -> str:
        """Traduz flags principais para orientações práticas sem inventar confiança."""
        labels = {
            'PERSPECTIVA_NAO_CORRIGIDA': 'A escala do círculo não corrige perspectiva.',
            'PLANO_COPLANAR_NAO_VERIFICADO': 'Confirme que marcador e segmento estão na mesma profundidade.',
            'TAG_AUSENTE_INCLINADA_OU_AMBIGUA': 'Não foi possível validar uma única tag verde. Confira cor, foco, inclinação e enquadramento.',
            'ARUCO_AUSENTE_OU_AMBIGUO': 'Não foi encontrado um único ArUco com o ID informado.',
            'NENHUM_BRACO_MENSURAVEL': 'Não foi possível obter um segmento. Se os limites estiverem visíveis, tente marcá-los manualmente.',
            'MASCARA_FRAGMENTADA': 'A máscara está fragmentada; pode haver perda de pele.',
            'MASCARA_LIMITADA_PELO_CORREDOR': 'A região pode estar cortada nas laterais.',
            'PONTOS_MANUAIS_SEM_MASCARA_PESSOA': 'Modo manual: pele e corredor, sem máscara de pessoa. Confira possível inclusão do fundo.',
            'PELE_HEURISTICA': 'A detecção por cor pode excluir pele, pelos e sombras. Pele coberta pela tag não é recuperada.',
        }
        return '\n\n'.join(dict.fromkeys(labels.get(f, f.replace('_', ' ').capitalize()) for f in flags))

    def toggle(self) -> None:
        """Alterna a imagem original e a sobreposição selecionada."""
        if self.marking or self.busy:
            return
        i = self.arm_combo.current()
        self.shown = self.original if self.shown is not self.original else (self.overlays[i] if i >= 0 and self.overlays else self.original)
        self.draw()

    def save(self) -> None:
        """Exporta o resultado atual com parâmetros usados e flags de qualidade."""
        if self.busy or not self.report:
            return
        folder = filedialog.askdirectory(title='Escolher pasta para salvar o relatório')
        if folder:
            report, overlays = self.report, list(self.overlays)
            self.run_job('export', lambda: exportar(report, overlays, Path(folder)))

    def poll(self) -> None:
        """Recebe conclusão dos trabalhos na thread principal da interface."""
        try:
            kind, data, error = self.queue.get_nowait()
        except Empty:
            self.after(100, self.poll)
            return
        self.busy = False
        self.progress.stop()
        if error:
            self.status.set('Não foi possível concluir. Confira a mensagem e tente novamente.')
            messagebox.showerror('Não foi possível concluir', error)
        elif kind == 'load':
            self.path, self.original = data
            self.shown = self.original
            self.filename.configure(text=self.path.name)
            self.status.set('Foto carregada. Confira marcador e tamanho, depois escolha a análise automática ou marque os dois pontos.')
            self.draw()
        elif kind == 'analysis':
            self.report, self.overlays = data
            self.points = []
            self.arm_combo['values'] = [f"Segmento {i + 1} • {a['lado']}" for i, a in enumerate(self.report['bracos'])]
            if self.overlays:
                self.arm_combo.current(0)
                self.show_arm()
                self.status.set(f'{len(self.overlays)} segmento(s) estimado(s). Confira os limites antes de exportar.')
            else:
                self.shown = self.original
                self.draw()
                self.set_notes(self.quality_text(self.report['flags']))
                self.status.set('Sem medida confiável nesta tentativa. Veja as orientações ao lado.')
        elif kind == 'export':
            self.status.set(f'Resultados salvos em {data}')
            messagebox.showinfo('Exportação concluída', f'JSON, CSV e imagens salvos em:\n{data}')
        self.update_controls()
        self.after(100, self.poll)


def main() -> None:
    """Abre a interface; aceita foto inicial opcional para demonstração local."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imagem', type=Path)
    args = parser.parse_args()
    Aplicacao(args.imagem).mainloop()


if __name__ == '__main__':
    main()

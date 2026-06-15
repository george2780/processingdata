"""Procesamiento de ensayos mecánicos y generación de reportes en PDF.

Define dos jerarquías paralelas:

* ``Mechanical_test`` y subclases — una instancia por probeta. Cargan datos
  crudos, calculan carga máxima, tenacidad acumulada, primer pico y puntos
  característicos interpolados.
* ``Test_report`` y subclases — una instancia por corrida. Orquestan el
  pipeline ``add_tests`` → ``write_report`` (volcado celda a celda al template
  Excel) → ``convert_excel_to_pdf`` → ``make_plot_report`` → ``merge_pdfs`` →
  normalización de orientación → overlay de encabezado/pie.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence, Union

import numpy as np
import scipy as sp
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from test_data import import_data_text, import_data_excel, get_data_excel, write_multisheet_excel
from edit_pdfs import convert_excel_to_pdf, merge_pdfs, normalize_pdf_orientation, apply_header_footer_pdf

logger = logging.getLogger(__name__)

class Mechanical_test:
    """Clase base para ensayos mecánicos."""

    def __init__(self):
        self.sample_id: Union[int, str, None] = 0
        self.data: pd.DataFrame = pd.DataFrame()
        self.data_process: pd.DataFrame = pd.DataFrame()
        self.data_file: Union[str, Path, None] = 'data_file'
        self.maxLoad: float = 0.0
        self.minLoad: float = 0.0
        self.idx: dict = {'minLoad': 0, 'maxLoad': 0}

    def get_sample_id(self):
        return self.sample_id
    
    def get_data(self, data_file: Union[str, Path], data_source: str, variable_names: Sequence[str]) -> pd.DataFrame:
        """Carga datos desde archivo de texto (csv delimitado por tab) o excel.

        Args:
            data_file: Ruta al archivo.
            data_source: 'csv' o 'xlsx'.
            variable_names: nombres de columnas esperadas para asignar.
        """
        self.data_file = Path(data_file)
        if not self.data_file.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {self.data_file}")

        if data_source == 'csv':
            self.data = import_data_text(file_path=str(self.data_file), delimiter='auto', variable_names=variable_names)
        elif data_source == 'xlsx':
            self.data = import_data_excel(file_path=str(self.data_file), sheet_idx=0, variable_names=variable_names)
        else:
            raise ValueError("data_source no reconocido (use 'csv' o 'xlsx').")
        if self.data.empty:
            logger.warning("DataFrame vacío tras la importación de %s", self.data_file)
        return self.data

    def make_positive_data(self, columns: Sequence[str] | None = None) -> pd.DataFrame:
        """Convierte columnas numéricas a su valor absoluto (útil cuando el sentido del sensor invierte signo)."""
        if self.data.empty:
            raise ValueError("No hay datos cargados para procesar.")
        cols = [c for c in (columns or self.data.columns) if c in self.data.columns]
        self.data[cols] = self.data[cols].abs()
        return self.data

    def get_max_load(self) -> float:
        """Devuelve la carga máxima (en valor absoluto) y registra su índice."""
        if self.data.empty:
            raise ValueError("Cargue datos antes de calcular la carga máxima.")
        loads = self.data['Load'].abs()
        self.idx['maxLoad'] = int(loads.values.argmax())
        self.maxLoad = float(loads.max())
        return self.maxLoad

    def get_min_load(self) -> float:
        """Devuelve la carga mínima (en valor absoluto) y registra su índice."""
        if self.data.empty:
            raise ValueError("Cargue datos antes de calcular la carga mínima.")
        loads = self.data['Load'].abs()
        self.idx['minLoad'] = int(loads.values.argmin())
        self.minLoad = float(loads.min())
        return self.minLoad

    def get_interp_data(self, x_name: str, y_name: str, x_new_values: np.ndarray) -> np.ndarray:
        """Interpola valores Y para nuevos valores X usando interpolación lineal."""
        return np.interp(x_new_values, self.data[x_name].to_numpy(), self.data[y_name].to_numpy())

    def plot_data(
        self,
        x, y, xlim, ylim, title, xlabel, ylabel, legend,
        report_id, test_name, num_pag,
        final_pag: bool = False,
        superposed: bool = False,
    ):
        """Genera la figura individual de una probeta. Devuelve ``(fig, ax)``."""
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        if superposed:
            for i, (x_vals, y_vals) in enumerate(zip(x, y)):
                ax.plot(self.data_process[x_vals], self.data_process[y_vals], label=legend[i], linewidth=2)
        else:
            ax.plot(self.data_process[x], self.data_process[y], 'b-', label=legend[0], linewidth=2)
        ax.set(xlim=xlim, ylim=ylim)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.legend(fontsize=9)
        ax.grid(visible=True, which='both', linestyle='--')
        ax.minorticks_on()
        ax.set_position([0.10, 0.15, 0.70, 0.75])
        fig.text(0.05, 0.05, f"INF-LE {report_id}", fontsize=8, horizontalalignment='left')
        fig.text(0.5, 0.05, f"LEDI-{test_name}", fontsize=8, horizontalalignment='center')
        fig.text(0.85, 0.05, f"Pág. {num_pag}", fontsize=8, horizontalalignment='right')
        if final_pag:
            fig.text(0.85, 0.03, 'Fin del informe', fontsize=8, horizontalalignment='right')
        return fig, ax

    def close_figure(self, fig) -> None:
        """Cierra figura para liberar memoria."""
        plt.close(fig)

class Resistance_mechanical_test(Mechanical_test):
    """Ensayo mecánico de resistencia con procesamiento de datos hasta punto de caída."""

    def __init__(self):
        super().__init__()
        self.idx = {'i': 0, 'f': 0, 'maxLoad': 0}

    def preprocess_data(self) -> dict:
        """Normaliza datos y define el rango del 1% al 75% de la carga máxima."""
        super().make_positive_data()
        super().get_max_load()
        imaxP = self.idx['maxLoad']
        loads = self.data['Load'].to_numpy()
        self.idx['i'] = int(np.argmin(np.abs(loads[:imaxP + 1] - 0.01 * self.maxLoad)))
        self.idx['f'] = int(np.argmin(np.abs(loads[imaxP:] - 0.75 * self.maxLoad))) + imaxP
        self.data_process = self.data.loc[self.idx['i']:self.idx['f'], :]
        return self.idx

class Toughness_mechanical_test(Mechanical_test):
    """Ensayo mecánico de tenacidad con cálculo de energía y detección de picos."""

    def __init__(self):
        super().__init__()
        self.idx = {'i': 0, 'f': 0, 'iL': 0, 'maxLoad': 0}
        self.defl_cps = pd.DataFrame()

    def get_toughness(self) -> pd.Series:
        """Calcula la tenacidad como integral acumulativa de fuerza vs deflexión."""
        self.data['Toughness'] = sp.integrate.cumulative_trapezoid(
            y=self.data['Load'].to_numpy(),
            x=self.data['Deflection'].to_numpy(),
            initial=0,
        )
        return self.data['Toughness']

    def get_first_peak(self) -> int:
        """Detecta el primer pico significativo en la curva de carga."""
        peaks, _ = sp.signal.find_peaks(
            x=self.data['Load'].to_numpy(),
            height=0.5 * self.maxLoad,
            prominence=0.05 * self.maxLoad,
            width=10,
        )
        if len(peaks) == 0 or peaks[0] > self.idx['maxLoad']:
            self.idx['iL'] = self.idx['maxLoad']
        else:
            self.idx['iL'] = int(peaks[0])
        return self.idx['iL']
    
    def get_defl_cps(
        self,
        x_points: np.ndarray | None = None,
        x_col: str = 'Deflection',
        include_extra_cols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Calcula puntos característicos interpolando respecto a una columna x elegida.

        Args:
            x_points: Puntos del eje x (en unidades de ``x_col``) donde evaluar.
            x_col: Columna a usar como eje x para la interpolación (por ejemplo, 'Deflection' o 'CMOD').
            include_extra_cols: Columnas adicionales a incluir (si existen), además de ['Load', 'Toughness'] y ``x_col``.

        Returns:
            DataFrame con filas en los índices característicos [iL, maxLoad, f] y filas interpoladas en ``x_points``.
        """
        if x_points is None:
            x_points = np.array([])

        if x_col not in self.data.columns:
            raise ValueError(f"Columna x '{x_col}' no existe en los datos. Disponibles: {self.data.columns.tolist()}")

        base_cols = ['Load', 'Toughness']
        extra = list(include_extra_cols) if include_extra_cols else []
        cols_to_interp: List[str] = []
        for c in base_cols + extra:
            if c != x_col and c not in cols_to_interp and c in self.data.columns:
                cols_to_interp.append(c)

        # Interpolaciones respecto a x_col
        interp_dict = {x_col: x_points}
        for c in cols_to_interp:
            interp_dict[c] = self.get_interp_data(x_name=x_col, y_name=c, x_new_values=x_points)
        df_interp = pd.DataFrame(interp_dict)

        # Filas en índices singulares (iL, maxLoad, f)
        idx = [self.idx['iL'], self.idx['maxLoad'], self.idx['f']]
        keep_cols = [x_col] + cols_to_interp
        existing = self.data.loc[idx, [col for col in keep_cols if col in self.data.columns]].copy()
        for c in keep_cols:
            if c not in existing.columns:
                existing[c] = np.nan
        existing = existing[keep_cols]

        self.defl_cps = pd.concat([existing, df_interp], ignore_index=True)
        return self.defl_cps

    def preprocess_data(
        self,
        defl_points: np.ndarray | None = None,
        x_col: str = 'Deflection',
        include_extra_cols: Sequence[str] | None = None,
    ) -> dict:
        """Normaliza datos, calcula tenacidad y puntos característicos.

        Args:
            defl_points: Puntos del eje x (en unidades de ``x_col``) donde evaluar cps.
            x_col: Columna a usar como eje x para interpolar ('Deflection' o 'CMOD', según ensayo).
            include_extra_cols: Columnas adicionales a devolver en cps (si existen en datos).
        """
        if defl_points is None:
            defl_points = np.array([])
        super().make_positive_data()
        super().get_max_load()
        self.get_toughness()
        self.get_first_peak()
        imaxP = self.idx['maxLoad']
        loads = self.data['Load'].to_numpy()
        self.idx['i'] = int(np.argmin(np.abs(loads[:imaxP + 1] - 0.01 * self.maxLoad)))
        self.idx['f'] = len(self.data) - 1
        self.data_process = self.data.loc[self.idx['i']:, :]
        self.get_defl_cps(x_points=defl_points, x_col=x_col, include_extra_cols=include_extra_cols)
        return self.idx

class Axial_compression_test(Resistance_mechanical_test):
    """Ensayo de compresión axial con cálculo de área de sección y resistencia."""
    
    def __init__(self, sample_id=None, data_file=None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file
        self.area_sec: float = 0.0
        self.strength: float = 0.0
        self.correction_factor: float = 1.0

    def get_area_section(self, length_sec: Union[float, List[float]], section_type: str) -> float:
        """Calcula el área de la sección transversal según el tipo de geometría.
        
        Args:
            length_sec: Para circular/cuadrada: diámetro/lado. Para rectangular: [ancho, alto].
            section_type: 'circular', 'square', o 'rectangular'.
        """
        if section_type == 'circular':
            self.area_sec = np.pi * (length_sec / 2) ** 2
        elif section_type == 'square':
            self.area_sec = length_sec ** 2
        elif section_type == 'rectangular':
            if not isinstance(length_sec, (list, tuple)) or len(length_sec) != 2:
                raise ValueError("Para sección rectangular, length_sec debe ser [ancho, alto]")
            self.area_sec = length_sec[0] * length_sec[1]
        else:
            raise ValueError(f"Tipo de sección no reconocido: {section_type}. Use 'circular', 'square', o 'rectangular'.")
        return self.area_sec
    
    def get_strength(self, correction_factor: float = 1.0) -> float:
        """Calcula la columna de esfuerzo (``Stress``, MPa) y la resistencia máxima.

        Asume ``Load`` en kN y ``area_sec`` en mm² (diámetro/lado en mm), por lo
        que ``Stress = 1000 * |Load| / area_sec`` queda en MPa. El factor de
        corrección por esbeltez se aplica a toda la columna ``Stress`` y, por
        tanto, ``self.strength`` (su máximo) queda también corregido.

        Args:
            correction_factor: Factor de corrección por esbeltez (columna ``K``
                del reporte). Multiplica toda la curva de esfuerzo
                (``Stress corregido = K * Stress medido``), de modo que tanto la
                resistencia reportada como el gráfico Esfuerzo-Deformación quedan
                corregidos.
        """
        if self.area_sec <= 0:
            raise ValueError("Área de sección debe ser calculada primero y mayor que 0.")
        if self.data.empty or 'Load' not in self.data.columns:
            raise ValueError("Cargue datos con columna 'Load' antes de calcular la resistencia.")
        if correction_factor <= 0:
            raise ValueError(f"Factor de corrección por esbeltez debe ser mayor que 0: {correction_factor!r}")
        self.correction_factor = float(correction_factor)
        self.data['Stress'] = self.correction_factor * 1000.0 * self.data['Load'].abs() / self.area_sec
        self.strength = float(self.data['Stress'].max())
        return self.strength

    def get_strain(
        self,
        gauge_cols: Sequence[str] = ('SG1', 'SG2', 'SG3'),
        microstrain: bool = True,
    ) -> pd.Series:
        """Promedia 2-3 strain gauges y guarda la deformación unitaria en ``Strain``.

        Args:
            gauge_cols: Nombres de las columnas con lecturas de strain gauges.
            microstrain: Si True, divide por 1e6 (µε → mm/mm).
        """
        if self.data.empty:
            raise ValueError("Cargue datos antes de calcular la deformación.")
        cols = [c for c in gauge_cols if c in self.data.columns]
        if not cols:
            raise ValueError(
                f"Ninguna columna de {list(gauge_cols)} encontrada. Disponibles: {self.data.columns.tolist()}"
            )
        avg = self.data[cols].abs().mean(axis=1)
        if microstrain:
            avg = avg / 1e6
        self.data['Strain'] = avg
        return self.data['Strain']

class Flexion_test(Resistance_mechanical_test):
    """Ensayo de flexión con cálculo de momento flector y resistencia."""
    
    def __init__(self, sample_id=None, data_file=None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file
        self.moment: float = 0.0
        self.resistance: float = 0.0

    def get_moment(self, span_length: float) -> float:
        """Calcula el momento flector máximo para carga a los tercios en viga simplemente apoyada.

        Args:
            span_length: Luz de la viga (distancia entre apoyos).
        """
        self.moment = (self.maxLoad * span_length) / 6.0
        return self.moment
    
    def get_resistance(self, section_modulus: float) -> float:
        """Calcula la resistencia dividiendo momento máximo por módulo de sección.

        Args:
            section_modulus: Módulo de sección de la viga.
        """
        if section_modulus <= 0:
            raise ValueError("Módulo de sección debe ser mayor que 0.")
        self.resistance = self.moment / section_modulus
        return self.resistance
    
class Panels_toughness_test(Toughness_mechanical_test):
    """Ensayo de tenacidad específico para paneles."""
    
    def __init__(self, sample_id=None, data_file=None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file

class Panel_Beam_residual_strength_test(Toughness_mechanical_test):
    """Ensayo de resistencia residual específico para vigas y paneles, incluye medición CMOD."""
    
    def __init__(self, sample_id=None, data_file=None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file

    def get_defl_cps(
        self,
        x_points: np.ndarray | None = None,
        x_col: str = 'CMOD',
        include_extra_cols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Obtiene puntos característicos para vigas y paneles, permitiendo elegir el eje x (por defecto 'CMOD')."""
        extra_cols = list(include_extra_cols) if include_extra_cols else []
        if x_col.lower() == 'cmod' and 'Deflection' not in extra_cols:
            extra_cols.append('Deflection')
        if x_col.lower() == 'deflection' and 'CMOD' not in extra_cols:
            extra_cols.append('CMOD')
        return super().get_defl_cps(x_points=x_points, x_col=x_col, include_extra_cols=extra_cols)

class Beam_residual_strength_test(Toughness_mechanical_test):
    """Ensayo de tenacidad específico para vigas."""
    
    def __init__(self, sample_id=None, data_file=None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file

class Tapa_buzon_flexion_test(Resistance_mechanical_test):
    """Ensayo de flexion de tapas para buzones."""
    
    def __init__(self, sample_id=None, data_file=None, umbral_kN: float = 120.0):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file
        # Umbral de cumplimiento (kN) – por norma NTP 339.111: 120 kN por defecto
        self.umbral_kN: float = float(umbral_kN)
        self.resultado: str = ''

    def set_umbral(self, valor_kN: float) -> None:
        """Permite ajustar el umbral de cumplimiento (kN)."""
        self.umbral_kN = float(valor_kN)

    def get_resultado(self) -> str:
        """Devuelve 'Cumple' si maxLoad >= umbral, 'No cumple' si < umbral, o 'Sin datos' si no hay datos."""
        if self.data.empty:
            self.resultado = 'Sin datos'
        else:
            self.resultado = 'Cumple' if self.maxLoad >= self.umbral_kN else 'No cumple'
        return self.resultado

    def get_resumen(self) -> dict:
        """Pequeño resumen útil para reportes o depuración."""
        return {
            'sample_id': self.sample_id,
            'maxLoad_kN': self.maxLoad,
            'umbral_kN': self.umbral_kN,
            'resultado': self.resultado or self.get_resultado()
        }

class Test_report:
    """
    Clase para generar informes.

    Atributos:
        infle (str): Identificador de la prueba.
        subinfle (str): Subidentificador de la prueba.
        folder (str): Carpeta base donde se generan los archivos.
        standard (str): Norma aplicada en la prueba.
        client_id (str): Nombre de la empresa que realiza la prueba.
        samples_id (list): Identificadores de las muestras.

    Atributos de clase (sobre-escribibles por subclases):
        report_extension: Extensión del archivo Excel ('xlsm' por defecto, 'xlsx' para genéricos).
        _standards_map: Mapa {nombre_norma: lista_puntos_x} para ``set_defl_points``.
            Si está vacío, ``set_defl_points`` levanta un error.
        header_footer_pdf: Ruta al PDF de encabezado/pie (acreditado o no).
        num_1plot_pag: Número de página del primer plot (controla el rango de
            páginas exportadas desde Excel: ``pag_f = num_1plot_pag - 1``). Se
            puede sobreescribir por instancia pasándolo al constructor.
        start_row: Fila de la plantilla Excel correspondiente a la primera
            muestra, tanto para lectura (``add_tests``) como para escritura
            (``_cell_writes``). Cada subclase declara su valor según el layout
            de su plantilla; se puede sobreescribir por instancia pasándolo al
            constructor.
        data_file_pattern: Patrón del nombre del archivo de datos por muestra,
            relativo a la carpeta del informe. Acepta los marcadores ``{id}``
            (obligatorio), ``{infle}`` y ``{subinfle}``. Ejemplos:
            ``'Losa P{id}.xlsx'``, ``'{infle}-Viga {id}/specimen.dat'``.
            La extensión decide el cargador: ``.xlsx``/``.xlsm``/``.xls`` se
            leen como Excel; cualquier otra como texto delimitado.
        data_columns: Nombres asignados posicionalmente a las columnas del
            archivo de datos (el archivo crudo no trae encabezados confiables).
            Si el orden de columnas del equipo difiere del default, se
            sobreescribe por instancia. Debe incluir ``_required_columns``.
    """

    report_extension: str = 'xlsm'
    _standards_map: dict = {}
    header_footer_pdf: str = './formatos/formato_no_acreditado.pdf'
    num_1plot_pag: int = 4
    start_row: int = 16
    data_file_pattern: Union[str, None] = None
    data_columns: tuple = ()
    _required_columns: frozenset = frozenset()

    def __init__(
        self,
        infle=None,
        subinfle=None,
        folder=None,
        standard=None,
        client_id=None,
        samples_id=None,
        num_1plot_pag: int | None = None,
        start_row: int | None = None,
        data_file_pattern: str | None = None,
        data_columns: Sequence[str] | None = None,
    ):
        self.repor_id = {'infle': infle, 'subinfle': subinfle}
        self.standard_test = standard
        self.folder_path = folder
        self.client_id = client_id
        self.samples_id = list(samples_id) if samples_id else []
        self.tests = []
        self.excel_file = 'excel_file'
        self.plots_file = 'plots_file'
        self.report_file = 'report_file'
        self.defl_points = np.array([])
        if num_1plot_pag is not None:
            self.num_1plot_pag = num_1plot_pag
        if start_row is not None:
            if int(start_row) < 1:
                raise ValueError(f"start_row debe ser >= 1: {start_row!r}")
            self.start_row = int(start_row)
        if data_file_pattern is not None:
            if '{id}' not in data_file_pattern:
                raise ValueError(
                    f"El patrón de archivo debe contener el marcador {{id}}: {data_file_pattern!r}"
                )
            self.data_file_pattern = data_file_pattern
        if data_columns is not None:
            self.data_columns = tuple(data_columns)
        if self.data_columns:
            missing = set(self._required_columns) - set(self.data_columns)
            if missing:
                raise ValueError(
                    f"Faltan columnas requeridas por {type(self).__name__}: {sorted(missing)}. "
                    f"Columnas recibidas: {list(self.data_columns)}"
                )
        # Resuelve nombres de archivo (excel_file, plots_file, report_file) en base
        # a los identificadores ya asignados.
        self.set_report_files(extension=self.report_extension)

    def set_report_files(self, extension='xlsm'):
        """Configura los nombres de los archivos de informe."""
        infle = self.repor_id.get('infle', 'NA')
        subinfle = self.repor_id.get('subinfle', '')
        folder = Path(self.folder_path) if self.folder_path else Path('.')
        folder.mkdir(parents=True, exist_ok=True)
        n_samples = len(self.samples_id)
        if subinfle == '':
            base = f"INFLE_{infle}_{self.standard_test}_{self.client_id}"
        else:
            base = f"INFLE_{infle}-{subinfle}_{self.standard_test}_{self.client_id}"
        if n_samples == 0:
            excel_name = f"{base}.{extension}"
            pdf_name = f"{base}.pdf"
        else:
            excel_name = f"{base}_{n_samples}.{extension}"
            pdf_name = f"{base}_{n_samples}.pdf"
        self.excel_file = str(folder / excel_name)
        self.plots_file = str(folder / 'plots.pdf')
        self.report_file = str(folder / pdf_name)
        return self.excel_file, self.report_file
    
    def set_defl_points(self) -> np.ndarray:
        """Configura ``self.defl_points`` a partir del estándar y ``_standards_map``.

        Cada subclase declara ``_standards_map`` (atributo de clase) con la forma
        ``{'NORMA': [puntos...]}``. Si la norma no está registrada, levanta ValueError.
        """
        if not self._standards_map:
            raise ValueError(
                f"{type(self).__name__} no define _standards_map; no se puede resolver puntos de deflexión."
            )
        points = self._standards_map.get(self.standard_test)
        if not points:
            raise ValueError(f"Norma no reconocida: {self.standard_test}")
        self.defl_points = np.array(points)
        return self.defl_points

    def add_tests(self):
        return self.tests

    def _resolve_data_file(self, sample_id) -> Path:
        """Resuelve la ruta del archivo de datos de una muestra desde ``data_file_pattern``."""
        if not self.data_file_pattern:
            raise ValueError(
                f"{type(self).__name__} no define data_file_pattern; no se puede resolver el archivo de datos."
            )
        try:
            rel = self.data_file_pattern.format(
                id=sample_id,
                infle=self.repor_id.get('infle', ''),
                subinfle=self.repor_id.get('subinfle', ''),
            )
        except (KeyError, IndexError) as e:
            raise ValueError(
                f"Patrón de archivo inválido {self.data_file_pattern!r}: marcador no reconocido ({e}). "
                "Use {id}, {infle} y/o {subinfle}."
            )
        return Path(self.folder_path) / rel

    def _load_test_data(self, test) -> pd.DataFrame:
        """Carga ``test.data`` eligiendo el cargador según la extensión del archivo.

        ``.xlsx``/``.xlsm``/``.xls`` se leen como Excel; cualquier otra extensión
        (``.dat``, ``.txt``, ``.csv``) como texto delimitado vía
        ``_load_specimen_dat``. Usa ``self.data_columns`` como nombres de columnas.
        """
        cols = list(self.data_columns)
        suffix = Path(test.data_file).suffix.lower()
        if suffix in ('.xlsx', '.xlsm', '.xls'):
            return test.get_data(data_file=test.data_file, data_source='xlsx', variable_names=cols)
        return self._load_specimen_dat(test, cols)

    def _load_specimen_dat(self, test, variable_names: Sequence[str]) -> pd.DataFrame:
        """Carga ``test.data`` desde ``specimen.dat`` (ensayos residuales)."""
        test.data = import_data_text(
            file_path=str(test.data_file),
            delimiter='auto',
            variable_names=variable_names,
            debug_sample=False,
            auto_detect_header=True,
            min_valid_cols=3,
            warn_once=True,
            audit_log_dir=str(Path(self.folder_path) / "audits"),
        )
        return test.data

    def _cell_writes(self, i, test):
        """Celdas a escribir para ``test`` (índice ``i``).

        Cada subclase declara aquí el layout específico del template Excel
        emitiendo tuplas ``(sheet_name, (row, col), value)``. La base no escribe
        nada — devuelve un iterador vacío.
        """
        return iter(())

    def write_report(self):
        """Escribe los resultados a Excel consumiendo ``_cell_writes`` por muestra.

        Recolecta todas las celdas agrupadas por hoja y delega en
        ``write_multisheet_excel`` para abrir y guardar el libro una sola vez.
        """
        writes_by_sheet: dict = {}
        for i, test in enumerate(self.tests):
            for sheet, (row, col), value in self._cell_writes(i, test):
                writes_by_sheet.setdefault(sheet, []).append((row, col, value))
        if writes_by_sheet:
            write_multisheet_excel(file_path=self.excel_file, writes_by_sheet=writes_by_sheet)
        return self.report_file

    def plot_report_data(
        self,
        x, y, xlim, ylim, title, xlabel, ylabel,
        sample_name, test_name, num_pag,
        final_pag: bool = False,
    ):
        """Genera la figura comparativa que superpone todas las probetas."""
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        for test in self.tests:
            ax.plot(
                test.data_process[x],
                test.data_process[y],
                label=f'{sample_name} {test.get_sample_id()}',
                linewidth=2,
            )
        ax.set(xlim=xlim, ylim=ylim)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.legend(fontsize=9)
        ax.grid(visible=True, which='both', linestyle='--')
        ax.minorticks_on()
        ax.set_position([0.10, 0.15, 0.75, 0.75])
        fig.text(0.05, 0.05, f"INF-LE {self.repor_id['infle']}{self.repor_id['subinfle']}", fontsize=8, horizontalalignment='left')
        fig.text(0.5, 0.05, f"LEDI-{test_name}", fontsize=8, horizontalalignment='center')
        fig.text(0.85, 0.05, f"Pág. {num_pag}", fontsize=8, horizontalalignment='right')
        if final_pag:
            fig.text(0.85, 0.03, 'Fin del informe', fontsize=8, horizontalalignment='right')
        return fig, ax

    def make_plot_report(
        self,
        x, y, xlim, ylim, title, xlabel, ylabel,
        sample_name, test_name, num_1plot_pag,
        final_pag: bool = False,
        comparative: bool = False,
        x_comp=None, y_comp=None, xlim_comp=None, ylim_comp=None,
        title_comp=None, xlabel_comp=None, ylabel_comp=None,
    ):
        """Genera el PDF de gráficos de la corrida (un gráfico por probeta y eje).

        Si ``comparative`` es True, antepone una página con todas las probetas
        superpuestas usando los kwargs ``*_comp``. Los parámetros ``x``/``y``/
        ``xlim``/``ylim``/``title``/``xlabel``/``ylabel`` aceptan ya sea un
        valor escalar (un único gráfico por probeta) o una lista (varios
        gráficos por probeta); todas las listas deben tener la misma longitud.
        """
        with PdfPages(self.plots_file) as pdf_file:
            if comparative:
                fig_report, _ = self.plot_report_data(
                    x=x_comp, y=y_comp,
                    xlim=xlim_comp, ylim=ylim_comp,
                    title=title_comp, xlabel=xlabel_comp, ylabel=ylabel_comp,
                    sample_name=sample_name,
                    test_name=test_name,
                    num_pag=num_1plot_pag,
                    final_pag=final_pag,
                )
                pdf_file.savefig(fig_report)
                plt.close(fig_report)
                num_1plot_pag += 1

            # Normaliza escalares y listas a listas paralelas.
            x_list, y_list, xlim_list, ylim_list, title_list, xlabel_list, ylabel_list = [
                p if isinstance(p, list) else [p]
                for p in (x, y, xlim, ylim, title, xlabel, ylabel)
            ]
            num_plots = len(x_list)
            if not all(len(lst) == num_plots for lst in (y_list, xlim_list, ylim_list, title_list, xlabel_list, ylabel_list)):
                raise ValueError(
                    f"Todas las listas de parámetros de gráfico deben tener la misma longitud ({num_plots})."
                )

            for i, test in enumerate(self.tests):
                for j in range(num_plots):
                    cx, cy = x_list[j], y_list[j]
                    if cx not in test.data_process.columns or cy not in test.data_process.columns:
                        logger.warning(
                            "Columnas '%s'/'%s' no encontradas en data_process (disponibles: %s)",
                            cx, cy, test.data_process.columns.tolist(),
                        )
                        continue
                    is_final_page = (i == len(self.tests) - 1) and (j == num_plots - 1)
                    fig_test, _ = test.plot_data(
                        x=cx, y=cy,
                        xlim=xlim_list[j], ylim=ylim_list[j],
                        title=title_list[j],
                        xlabel=xlabel_list[j], ylabel=ylabel_list[j],
                        legend=[f'{sample_name} {test.get_sample_id()}'],
                        report_id=f"{self.repor_id['infle']}{self.repor_id['subinfle']}",
                        test_name=test_name,
                        num_pag=i * num_plots + j + num_1plot_pag,
                        final_pag=is_final_page,
                    )
                    pdf_file.savefig(fig_test)
                    plt.close(fig_test)

    def plot_spec(self) -> dict:
        """Devuelve los kwargs para ``make_plot_report`` (sin ``num_1plot_pag``).

        Las subclases concretas deben implementar este método con los textos, ejes
        y banderas de comparativo propios del ensayo. La base no dibuja nada.
        """
        raise NotImplementedError(
            f"{type(self).__name__} debe implementar plot_spec() o sobreescribir make_report_file()."
        )

    def make_report_file(self):
        """Pipeline canónico de generación del reporte.

        Orden: ``add_tests`` → ``write_report`` (escribe Excel) → ``convert_excel_to_pdf``
        → ``make_plot_report`` (genera ``plots.pdf``) → ``merge_pdfs`` → normalización
        de orientación → overlay de encabezado/pie. Las subclases parametrizan el
        pipeline vía atributos de clase (``header_footer_pdf``, ``num_1plot_pag``)
        y ``plot_spec()``.
        """
        self.add_tests()
        self.write_report()
        convert_excel_to_pdf(
            excel_path=self.excel_file,
            pdf_path=self.report_file,
            pag_i=1,
            pag_f=self.num_1plot_pag - 1,
        )
        self.make_plot_report(num_1plot_pag=self.num_1plot_pag, **self.plot_spec())
        merge_pdfs(pdf_list=[self.report_file, self.plots_file], output_pdf=self.report_file)
        normalize_pdf_orientation(
            input_pdf_path=self.report_file,
            output_pdf_path=self.report_file,
            desired_orientation='portrait',
        )
        apply_header_footer_pdf(
            input_pdf_path=self.report_file,
            header_footer_pdf_path=self.header_footer_pdf,
            output_pdf_path=self.report_file,
        )
        return self.report_file

class Panel_toughness_test_report(Test_report):
    """Reporte de tenacidad por flexión en paneles (ASTM C1550 / EFNARC / EN 14488-5)."""

    _standards_map = {
        'ASTMC1550': [5., 10., 20., 30., 40., 45.],
        'EFNARC1996': [5., 10., 15., 20., 25., 30.],
        'EFNARC1999': [5., 10., 15., 20., 25., 30.],
        'EN14488-5': [5., 10., 15., 20., 25., 30.],
    }
    num_1plot_pag = 4
    start_row = 18
    data_file_pattern = 'Losa P{id}.xlsx'
    data_columns = ('Time', 'Deflection', 'Displacement', 'Load')
    _required_columns = frozenset({'Load', 'Deflection'})

    def add_tests(self):
        """Agrega pruebas basadas en los identificadores de muestras."""
        self.set_defl_points()

        for id in self.samples_id:
            test = Panels_toughness_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            # ASTM C1550 / EFNARC / EN 14488-5: puntos característicos sobre deflexión.
            test.preprocess_data(defl_points=self.defl_points, x_col='Deflection')
            self.tests.append(test)

    def _cell_writes(self, i, test):
        # Layout 'Resultados': bloque de 3 filas (load, deflection, toughness) por
        # muestra, una columna por punto de deflexión.
        SHEET = 'Resultados'
        row_start = 5 * i + self.start_row
        defl_cps = test.defl_cps
        for j, (deflection, load, toughness) in enumerate(
            zip(defl_cps['Deflection'], defl_cps['Load'], defl_cps['Toughness'])
        ):
            col = 4 + j
            yield SHEET, (row_start + 0, col), load
            yield SHEET, (row_start + 1, col), deflection
            yield SHEET, (row_start + 2, col), toughness

    def plot_spec(self) -> dict:
        return {
            'x': 'Deflection',
            'y': 'Load',
            'xlim': (0, self.defl_points[-1]),
            'ylim': (0, None),
            'title': 'Fuerza-Deflexión',
            'xlabel': 'Deflexión (mm)',
            'ylabel': 'Fuerza (kN)',
            'sample_name': 'PANEL',
            'test_name': 'ENSAYO DE TENACIDAD POR FLEXIÓN',
            'comparative': True,
            'x_comp': 'Deflection',
            'y_comp': 'Toughness',
            'xlim_comp': (0, self.defl_points[-1]),
            'ylim_comp': (0, None),
            'title_comp': 'Energía-Deflexión',
            'xlabel_comp': 'Deflexión (mm)',
            'ylabel_comp': 'Energía (J)',
        }

class Panel_Beam_residual_strength_test_report(Test_report):
    """Reporte de resistencia residual con CMOD para vigas/paneles (EN 14651 / EN 14488)."""

    _standards_map = {
        'EN14651': [0.5, 1.5, 2.5, 3.5, 4.],
        'EN14488': [0.5, 1.5, 2.5, 3.5, 4., 5.],
    }
    num_1plot_pag = 5
    start_row = 19
    data_file_pattern = '{infle}-Viga {id}/specimen.dat'
    data_columns = ('Time', 'Displacement', 'Load', 'CMOD', 'Deflection')
    _required_columns = frozenset({'Load', 'CMOD', 'Deflection'})

    def add_tests(self):
        """Agrega pruebas basadas en los identificadores de muestras."""
        self.set_defl_points()

        for id in self.samples_id:
            test = Panel_Beam_residual_strength_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            # EN 14651 / EN 14488: puntos característicos definidos sobre CMOD.
            test.preprocess_data(defl_points=self.defl_points, x_col='CMOD', include_extra_cols=['Deflection'])
            self.tests.append(test)

    def _cell_writes(self, i, test):
        # Layout 'ResistenciaResidual' (CMOD): una fila por muestra, bloques de 4
        # columnas (1000*load, deflection, cmod, toughness) por punto CMOD.
        # Nota: la carga se escala ×1000 (kN → N) para la plantilla.
        SHEET = 'ResistenciaResidual'
        row = i + self.start_row
        defl_cps = test.defl_cps
        for j, (load, deflection, cmod, toughness) in enumerate(
            zip(defl_cps['Load'], defl_cps['Deflection'], defl_cps['CMOD'], defl_cps['Toughness'])
        ):
            col_start = 20 + 4 * j
            yield SHEET, (row, col_start + 0), 1000 * load
            yield SHEET, (row, col_start + 1), deflection
            yield SHEET, (row, col_start + 2), cmod
            yield SHEET, (row, col_start + 3), toughness

    def plot_spec(self) -> dict:
        return {
            'x': ['Deflection', 'CMOD'],
            'y': ['Load', 'Load'],
            'xlim': [(0, self.defl_points[-1]), (0, None)],
            'ylim': [(0, None), (0, None)],
            'title': ['Fuerza-Deflexión', 'Fuerza-CMOD'],
            'xlabel': ['Deflexión (mm)', 'CMOD (mm)'],
            'ylabel': ['Fuerza (kN)', 'Fuerza (kN)'],
            'sample_name': 'VIGA',
            'test_name': 'ENSAYO DE RESISTENCIA RESIDUAL EN FLEXIÓN',
            'comparative': True,
            'x_comp': 'Deflection',
            'y_comp': 'Toughness',
            'xlim_comp': (0, self.defl_points[-1]),
            'ylim_comp': (0, None),
            'title_comp': 'Energía-Deflexión',
            'xlabel_comp': 'Deflexión (mm)',
            'ylabel_comp': 'Energía (J)',
        }

class Beam_residual_strength_test_report(Test_report):
    """Reporte de resistencia residual de vigas por deflexión (ASTM C1609)."""

    _standards_map = {
        'ASTMC1609': [0.75, 3.],
    }
    num_1plot_pag = 4
    start_row = 19
    data_file_pattern = '{infle}-Viga {id}/specimen.dat'
    data_columns = ('Time', 'Displacement', 'Load', 'Deflection', 'Deflection2')
    _required_columns = frozenset({'Load', 'Deflection'})

    def add_tests(self):
        """Agrega pruebas basadas en los identificadores de muestras."""
        self.set_defl_points()

        for id in self.samples_id:
            test = Beam_residual_strength_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            # ASTM C1609: puntos característicos definidos sobre deflexión.
            test.preprocess_data(defl_points=self.defl_points, x_col='Deflection')
            self.tests.append(test)

    def _cell_writes(self, i, test):
        # Layout 'ResistenciaResidual' (deflexión, ASTM C1609): una fila por muestra,
        # bloques de 3 columnas (1000*load, deflection, toughness) por punto.
        # Nota: la carga se escala ×1000 (kN → N) para la plantilla.
        SHEET = 'ResistenciaResidual'
        row = i + self.start_row
        defl_cps = test.defl_cps
        for j, (load, deflection, toughness) in enumerate(
            zip(defl_cps['Load'], defl_cps['Deflection'], defl_cps['Toughness'])
        ):
            col_start = 21 + 3 * j
            yield SHEET, (row, col_start + 0), 1000 * load
            yield SHEET, (row, col_start + 1), deflection
            yield SHEET, (row, col_start + 2), toughness

    def plot_spec(self) -> dict:
        return {
            'x': 'Deflection',
            'y': 'Load',
            'xlim': (0, self.defl_points[-1]),
            'ylim': (0, None),
            'title': 'Fuerza-Deflexión',
            'xlabel': 'Deflexión (mm)',
            'ylabel': 'Fuerza (kN)',
            'sample_name': 'VIGA',
            'test_name': 'ENSAYO DE RESISTENCIA RESIDUAL EN FLEXIÓN',
            'comparative': True,
            'x_comp': 'Deflection',
            'y_comp': 'Toughness',
            'xlim_comp': (0, self.defl_points[-1]),
            'ylim_comp': (0, None),
            'title_comp': 'Energía-Deflexión',
            'xlabel_comp': 'Deflexión (mm)',
            'ylabel_comp': 'Energía (J)',
        }

class Axial_compression_test_report(Test_report):
    """Reporte de compresión axial de testigos (cores) de hormigón."""

    header_footer_pdf = './formatos/formato_acreditado.pdf'
    num_1plot_pag = 5
    start_row = 16
    # data_file_pattern = None: por defecto intenta '{infle}-d{id}/specimen.dat'
    # y cae a '{infle}-d{id}.xlsx'. Si se da un patrón explícito, se usa solo ese.
    data_columns = ('Time', 'Displacement', 'Load')
    _required_columns = frozenset({'Load', 'Displacement'})
    # Layout 'Cores': por muestra, fila i+start_row (16 por defecto). Columna
    # F=6 (diámetro mm), K=11 (factor de corrección por esbeltez),
    # N=14 (resistencia MPa), O=15 (resistencia kgf/cm²), W=23 (carga máx kN).
    # 1 MPa = 10.1972 kgf/cm².
    _MPA_TO_KGFCM2 = 10.1972

    def _read_template_geometry(self, i):
        """Lee diámetro (F) y factor de esbeltez (K) de la fila ``i + start_row``."""
        row = i + self.start_row
        diameter = get_data_excel(
            file_path=self.excel_file,
            sheet_idx='Cores',
            position=(row, 6),
        )
        if diameter is None or float(diameter) <= 0:
            raise ValueError(f"Diámetro inválido en 'Cores'!F{row}: {diameter!r}")
        k_factor = get_data_excel(
            file_path=self.excel_file,
            sheet_idx='Cores',
            position=(row, 11),
        )
        if k_factor is None or float(k_factor) <= 0:
            raise ValueError(f"Factor de corrección por esbeltez inválido en 'Cores'!K{row}: {k_factor!r}")
        return float(diameter), float(k_factor)

    def add_tests(self):
        for i, id in enumerate(self.samples_id):
            diameter, k_factor = self._read_template_geometry(i)
            if self.data_file_pattern:
                data_path = self._resolve_data_file(id)
                if not data_path.exists():
                    raise FileNotFoundError(f"No se encontró archivo de datos para muestra {id}: {data_path}")
                logger.info(f"Muestra {id}: usando {data_path}")
                test = Axial_compression_test(sample_id=id, data_file=str(data_path))
                self._load_test_data(test)
            else:
                dat_path = Path(self.folder_path) / f"{self.repor_id['infle']}-d{id}" / "specimen.dat"
                xlsx_path = Path(self.folder_path) / f"{self.repor_id['infle']}-d{id}.xlsx"
                if dat_path.exists():
                    logger.info(f"Muestra {id}: usando specimen.dat ({dat_path})")
                    test = Axial_compression_test(sample_id=id, data_file=str(dat_path))
                elif xlsx_path.exists():
                    logger.info(f"Muestra {id}: usando xlsx alternativo ({xlsx_path})")
                    test = Axial_compression_test(sample_id=id, data_file=str(xlsx_path))
                else:
                    raise FileNotFoundError(
                        f"No se encontró archivo de datos para muestra {id}: "
                        f"ni {dat_path} ni {xlsx_path}"
                    )
                self._load_test_data(test)
            test.get_area_section(length_sec=float(diameter), section_type='circular')
            test.get_strength(correction_factor=float(k_factor))
            test.preprocess_data()
            self.tests.append(test)

    def _cell_writes(self, i, test):
        SHEET = 'Cores'
        row = i + self.start_row
        yield SHEET, (row, 14), test.strength
        yield SHEET, (row, 15), test.strength * self._MPA_TO_KGFCM2
        yield SHEET, (row, 23), test.get_max_load()

    def plot_spec(self) -> dict:
        return {
            'x': 'Displacement',
            'y': 'Load',
            'xlim': (0, None),
            'ylim': (0, None),
            'title': 'Fuerza-Desplazamiento',
            'xlabel': 'Desplazamiento (mm)',
            'ylabel': 'Fuerza (kN)',
            'sample_name': 'CORE',
            'test_name': 'ENSAYO DE RESISTENCIA A LA COMPRESIÓN',
            'comparative': False,
        }

class Axial_compression_local_test_report(Axial_compression_test_report):
    """Compresión axial con strain gauges (curva esfuerzo-deformación adicional).

    Diferencias respecto a ``Axial_compression_test_report``:
        - El archivo de datos por probeta tiene columnas
          ``[Time, Load, Displacement, SG1, SG2, SG3]`` (SG en µε).
        - Se agrega un segundo gráfico Esfuerzo-Deformación al informe.

    Hereda de la clase base la lectura del diámetro (``'Cores'!F{i+start_row}``)
    y la escritura de resistencia/maxLoad en columnas N/O/W.
    """

    data_file_pattern = '{infle}-d{id}.xlsx'
    data_columns = ('Time', 'Load', 'Displacement', 'SG1', 'SG2', 'SG3')
    _required_columns = frozenset({'Load', 'Displacement'})

    def add_tests(self):
        for i, id in enumerate(self.samples_id):
            diameter, k_factor = self._read_template_geometry(i)
            test = Axial_compression_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            test.get_area_section(length_sec=float(diameter), section_type='circular')
            test.get_strength(correction_factor=float(k_factor))
            test.get_strain()
            test.preprocess_data()
            self.tests.append(test)

    def plot_spec(self) -> dict:
        return {
            'x': ['Displacement', 'Strain'],
            'y': ['Load', 'Stress'],
            'xlim': [(0, None), (0, None)],
            'ylim': [(0, None), (0, None)],
            'title': ['Fuerza-Desplazamiento', 'Esfuerzo-Deformación'],
            'xlabel': ['Desplazamiento (mm)', 'Deformación unitaria (mm/mm)'],
            'ylabel': ['Fuerza (kN)', 'Esfuerzo (MPa)'],
            'sample_name': 'CORE',
            'test_name': 'ENSAYO DE RESISTENCIA A LA COMPRESIÓN',
            'comparative': False,
        }

class Tapa_buzon_flexion_test_report(Test_report):
    """Reporte de ensayo de flexión (tránsito) de tapas de buzón (NTP 339.111)."""

    header_footer_pdf = './formatos/formato_acreditado.pdf'
    num_1plot_pag = 4
    start_row = 26
    data_file_pattern = 'tapas_{id}.xlsx'
    data_columns = ('Time', 'Load')
    _required_columns = frozenset({'Time', 'Load'})

    def add_tests(self):
        for id in self.samples_id:
            test = Tapa_buzon_flexion_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            test.preprocess_data()
            self.tests.append(test)

    def _cell_writes(self, i, test):
        # Layout 'Tapa C°A°': bloque de 3 filas por muestra desde start_row.
        yield 'Tapa C°A°', (3 * i + self.start_row, 17), test.get_max_load()

    def plot_spec(self) -> dict:
        return {
            'x': 'Time',
            'y': 'Load',
            'xlim': (0, None),
            'ylim': (0, None),
            'title': 'Fuerza',
            'xlabel': 'Tiempo (seg)',
            'ylabel': 'Fuerza (kN)',
            'sample_name': 'TAPA',
            'test_name': 'ENSAYO DE RESISTENCIA AL TRÁNSITO',
            'comparative': False,
        }

class Beam_flexion_test_report(Test_report):
    """Reporte de ensayo de flexión en vigas."""

    header_footer_pdf = './formatos/formato_acreditado.pdf'
    num_1plot_pag = 4
    start_row = 16
    data_file_pattern = 'vigas_{id}.xlsx'
    data_columns = ('Time', 'Load', 'Deflection')
    _required_columns = frozenset({'Load', 'Deflection'})

    def add_tests(self):
        for id in self.samples_id:
            test = Flexion_test(
                sample_id=id,
                data_file=str(self._resolve_data_file(id)),
            )
            self._load_test_data(test)
            test.preprocess_data()
            self.tests.append(test)

    def _cell_writes(self, i, test):
        yield 'Vigas', (i + self.start_row, 17), test.get_max_load()

    def plot_spec(self) -> dict:
        return {
            'x': 'Deflection',
            'y': 'Load',
            'xlim': (0, None),
            'ylim': (0, None),
            'title': 'Fuerza-Deflexión',
            'xlabel': 'Deflexión (mm)',
            'ylabel': 'Fuerza (kN)',
            'sample_name': 'VIGA',
            'test_name': 'ENSAYO DE FLEXIÓN',
            'comparative': False,
        }

class Generate_test_report(Test_report):
    """Reporte genérico: convierte un Excel ya preparado por el usuario a PDF."""

    report_extension = 'xlsx'

    def make_report_file(self):
        """Flujo especial: sólo conversión Excel→PDF + overlay (sin plots ni merge).

        Exporta el libro completo (sin rango de páginas). No llama a ``add_tests``
        ni ``write_report``: el Excel ya viene preparado por el usuario.
        """
        convert_excel_to_pdf(
            excel_path=self.excel_file,
            pdf_path=self.report_file,
        )
        normalize_pdf_orientation(
            input_pdf_path=self.report_file,
            output_pdf_path=self.report_file,
            desired_orientation='portrait',
        )
        apply_header_footer_pdf(
            input_pdf_path=self.report_file,
            header_footer_pdf_path=self.header_footer_pdf,
            output_pdf_path=self.report_file,
        )
        return self.report_file


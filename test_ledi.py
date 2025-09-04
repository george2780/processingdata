import numpy as np
import scipy as sp
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from test_data import import_data_text, import_data_excel, get_data_excel, write_data_excel
from edit_pdfs import convert_excel_to_pdf, merge_pdfs, normalize_pdf_orientation, apply_header_footer_pdf

class Mechanical_test:
    def __init__(self):
        self.sample_id = 0
        self.data = pd.DataFrame()
        self.data_process = pd.DataFrame()
        self.data_file = 'data_file'
        self.maxLoad = 0
        self.minLoad = 0
        self.idx = {'minLoad': 0, 'maxLoad': 0}

    def get_sample_id(self):
        return self.sample_id
    
    def get_data(self, data_file, data_source, variable_names):
        self.data_file = data_file    
        if data_source == 'csv':
            self.data = import_data_text(file_path=self.data_file, delimiter='\t', variable_names=variable_names)
        elif data_source == 'xlsx':
            self.data = import_data_excel(file_path=self.data_file, sheet_idx=0, variable_names=variable_names)
        else:
            print("Error: data_source not recognized.")
        return self.data
            
    def make_positive_data(self, columns=None):
        columns = columns or self.data.columns  # Procesa todas las columnas si no se especifica
        for col in columns:
            self.data[col] = np.abs(self.data[col])
        return self.data
    
    def get_max_load(self):
        if self.data.empty:
            raise ValueError("Error: load data before calculating the maximum load.")
        else:
            self.idx['maxLoad'] = np.argmax(np.abs(self.data['Load'].to_numpy()))
            self.maxLoad = np.max(self.data['Load'].to_numpy())
        return self.maxLoad
    
    def get_min_load(self):
        if self.data.empty:
            raise ValueError("Error: load data before calculating the maximum load.")
        else:
            self.idx['minLoad'] = np.argmin(np.abs(self.data['Load'].to_numpy()))
            self.minLoad = np.min(self.data['Load'].to_numpy())
        return self.maxLoad
    
    def get_interp_data(self, x_name, y_name, x_new_values):
        x = self.data[x_name].to_numpy()
        y = self.data[y_name].to_numpy()
        y_new_values = np.interp(x_new_values, x, y)
        return y_new_values

    def plot_data(self, x, y, xlim, ylim, title, xlabel, ylabel, legend, report_id, test_name, num_pag, final_pag=False, superposed=False):
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        if superposed:
            # Trazar múltiples curvas en el mismo gráfico
            for i, (x_vals, y_vals) in enumerate(zip(x, y)):
                ax.plot(
                    self.data_process[x_vals], 
                    self.data_process[y_vals], 
                    label=legend[i], 
                    linewidth=2
                )
        else:
            # Trazar una única curva
            ax.plot(self.data_process[x], self.data_process[y], 'b-', label=legend[0], linewidth=2)
        # Configuración común del gráfico
        ax.set(xlim=xlim, ylim=ylim)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.legend(fontsize=9)
        ax.grid(visible=True, which='both', linestyle='--')
        ax.minorticks_on()
        ax.set_position([0.10, 0.15, 0.65, 0.75])           #MARGENES DE IMPRESIÓN PARA DIAMANTINAS
        #ax.set_position([0.10, 0.15, 0.75, 0.75])           #MARGENES DE IMPRESIÓN PARA PANELES
        # Texto adicional en el gráfico
        fig.text(0.05, 0.05, f'INF-LE {report_id}', fontsize=8, horizontalalignment='left')
        fig.text(0.5, 0.05, f'LEDI-{test_name}', fontsize=8, horizontalalignment='center')
        fig.text(0.85, 0.05, f'Pág. {num_pag}', fontsize=8, horizontalalignment='right')
        if final_pag:
            fig.text(0.85, 0.03, 'Fin del informe', fontsize=8, horizontalalignment='right')
        return fig, ax

class Resistance_mechanical_test(Mechanical_test):
    def __init__(self):
        super().__init__()
        self.idx = {'i': 0, 'f': 0, 'maxLoad': 0}

    def preprocess_data(self):
        super().make_positive_data()
        super().get_max_load()
        imaxP = self.idx['maxLoad']
        self.idx['i'] = np.argmin(np.abs(self.data.loc[:imaxP, 'Load'].to_numpy() - 0.01 * self.maxLoad))
        self.idx['f'] = np.argmin(np.abs(self.data.loc[imaxP:, 'Load'].to_numpy() - 0.75 * self.maxLoad)) + imaxP
        self.data_process = self.data.loc[self.idx['i']:self.idx['f'], :]
        return self.idx

class Toughness_mechanical_test(Mechanical_test):
    def __init__(self):
        super().__init__()
        self.idx = {'i': 0, 'f': 0, 'iL':0, 'maxLoad': 0}
        self.defl_cps = pd.DataFrame()

    def get_toughness(self):
        toughness = sp.integrate.cumulative_trapezoid(y=self.data['Load'].to_numpy(), x=self.data['Deflection'].to_numpy(), initial=0)
        self.data['Toughness'] = toughness
        return self.data['Toughness']
    
    def get_first_peak(self):
        peaks, _ = sp.signal.find_peaks(x=self.data['Load'].to_numpy(), height=0.1*self.maxLoad, prominence=0.1*self.maxLoad, width=10)
        if len(peaks) == 0 or peaks[0] > self.idx['maxLoad']:
            self.idx['iL'] = self.idx['maxLoad']
        else:
            self.idx['iL'] = peaks[0]
        return self.idx['iL']
    
    def get_defl_cps(self, defl_points=np.array([])):
        loads = self.get_interp_data(x_name='Deflection', y_name='Load', x_new_values=defl_points)
        toughness = self.get_interp_data(x_name='Deflection', y_name='Toughness', x_new_values=defl_points)
        idx = [self.idx['iL'], self.idx['maxLoad'], self.idx['f']]
        self.defl_cps = pd.concat([
            self.data.loc[idx, ['Deflection', 'Load', 'Toughness']],
            pd.DataFrame({'Deflection': defl_points, 'Load': loads, 'Toughness': toughness})
            ])
        return self.defl_cps

    def preprocess_data(self, defl_points=np.array([])):
        super().make_positive_data()
        super().get_max_load()
        self.get_toughness()
        self.get_first_peak()
        imaxP = self.idx['maxLoad']
        self.idx['i'] = np.argmin(np.abs(self.data.loc[:imaxP, 'Load'].to_numpy() - 0.01 * self.maxLoad))
        self.idx['f'] = len(self.data)-1
        self.data_process = self.data.loc[self.idx['i']:, :]
        self.get_defl_cps(defl_points)
        return self.idx

class Axial_compression_test(Resistance_mechanical_test):
    def __init__(self, sample_id=None, data_file= None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file
        self.area_sec = 0
        self.strength = 0

    def get_area_section(self, length_sec=None, section_type=None):
        if section_type=='circular':
            self.area_sec = np.pi*(length_sec/2)**2
        elif section_type=='square':
            self.area_sec = length_sec**2
        elif section_type=='rectangular':
            self.area_sec = length_sec[0]*length_sec[1]
        else:
            print("Error: no section type selected.")
        return self.area_sec
    
    def get_strength(self):
        self.strength = self.maxLoad/self.area_sec
        return self.strength
    
class Panels_toughness_test(Toughness_mechanical_test):
    def __init__(self, sample_id=None, data_file= None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file

class Beams_residual_strength_test(Toughness_mechanical_test):
    def __init__(self, sample_id=None, data_file= None):
        super().__init__()
        self.sample_id = sample_id
        self.data_file = data_file

    def get_defl_cps(self, defl_points=np.array([])):
        loads = self.get_interp_data(x_name='Deflection', y_name='Load', x_new_values=defl_points)
        toughness = self.get_interp_data(x_name='Deflection', y_name='Toughness', x_new_values=defl_points)
        cmods = self.get_interp_data(x_name='Deflection', y_name='CMOD', x_new_values=defl_points)
        idx = [self.idx['iL'], self.idx['maxLoad'], self.idx['f']]
        self.defl_cps = pd.concat([
            self.data.loc[idx, ['Deflection', 'CMOD', 'Load', 'Toughness']],
            pd.DataFrame({'Deflection': defl_points, 'CMOD': cmods, 'Load': loads, 'Toughness': toughness})
            ])
        return self.defl_cps

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
    """
    def __init__(self):
        self.repor_id = {'infle': 'infle', 'subinfle': 'subinfle'}
        self.standard_test = 'standard'
        self.folder_path = 'folder'
        self.client_id = 'empresa'
        self.samples_id = []
        self.tests = []
        self.excel_file = 'excel_file'
        self.plots_file = 'plots_file'
        self.report_file = 'report_file'

    def set_report_files(self, extension='xlsm'):
        """Configura los nombres de los archivos de informe."""
        if len(self.samples_id) == 0:
            self.excel_file = f'{self.folder_path}INFLE_{self.repor_id['infle']}{self.repor_id['subinfle']}_{self.standard_test}_{self.client_id}.{extension}'
            self.plots_file = f'{self.folder_path}plots.pdf'
            self.report_file = f'{self.folder_path}INFLE_{self.repor_id['infle']}{self.repor_id['subinfle']}_{self.standard_test}_{self.client_id}.pdf'
        elif len(self.samples_id) > 0:
            self.excel_file = f'{self.folder_path}INFLE_{self.repor_id['infle']}{self.repor_id['subinfle']}_{self.standard_test}_{self.client_id}_{len(self.samples_id)}.{extension}'
            self.plots_file = f'{self.folder_path}plots.pdf'
            self.report_file = f'{self.folder_path}INFLE_{self.repor_id['infle']}{self.repor_id['subinfle']}_{self.standard_test}_{self.client_id}_{len(self.samples_id)}.pdf'
        else:
            raise ValueError("Error: No se han definido los identificadores de la prueba o de las muestras.")
        return self.excel_file, self.report_file
    
    def add_tests(self):
        return self.tests
    
    def write_report(self):
        return self.report_file

    def plot_report_data(self, x, y, xlim, ylim, title, xlabel, ylabel, sample_name, test_name, num_pag, final_pag=False):
            # Preparar datos para gráficos superpuestos
            fig, ax = plt.subplots(figsize=(11.7, 8.3))
            legends = [f'{sample_name} {test.get_sample_id()}' for test in self.tests]
            for i, test in enumerate(self.tests):
                data = test.data_process
                ax.plot(data[x], data[y], label=legends[i], linewidth=2)
            # Configuración común del gráfico
            ax.set(xlim=xlim, ylim=ylim)
            ax.set_title(title, fontsize=10)
            ax.set_xlabel(xlabel, fontsize=9)
            ax.set_ylabel(ylabel, fontsize=9)
            ax.legend(fontsize=9)
            ax.grid(visible=True, which='both', linestyle='--')
            ax.minorticks_on()
            ax.set_position([0.10, 0.15, 0.75, 0.75])
            # Texto adicional en el gráfico
            fig.text(0.05, 0.05, f'INF-LE {self.repor_id['infle']}{self.repor_id['subinfle']}', fontsize=8, horizontalalignment='left')
            fig.text(0.5, 0.05, f'LEDI-{test_name}', fontsize=8, horizontalalignment='center')
            fig.text(0.85, 0.05, f'Pág. {num_pag}', fontsize=8, horizontalalignment='right')
            if final_pag:
                fig.text(0.85, 0.03, 'Fin del informe', fontsize=8, horizontalalignment='right')
            return fig, ax

    def make_plot_report(
            self, x, y, xlim, ylim, title, xlabel, ylabel, sample_name, test_name, num_1plot_pag, final_pag=False,
            comparative=False, x_comp=None, y_comp=None, xlim_comp=None, ylim_comp=None, title_comp=None, xlabel_comp=None, ylabel_comp=None):
        """Genera gráficos de los resultados."""
        with PdfPages(self.plots_file) as pdf_file:
            if comparative:
                fig_report, _ = self.plot_report_data(
                    x=x_comp,
                    y=y_comp,
                    xlim=xlim_comp,
                    ylim=ylim_comp,
                    title=title_comp,
                    xlabel=xlabel_comp,
                    ylabel=ylabel_comp,
                    sample_name=sample_name,
                    test_name=test_name,
                    num_pag=num_1plot_pag,
                    final_pag=final_pag
                    )
                pdf_file.savefig(fig_report)
                num_1plot_pag += 1
            
            # Handle both string and list inputs for plotting parameters
            x_list = x if isinstance(x, list) else [x]
            y_list = y if isinstance(y, list) else [y]
            xlim_list = xlim if isinstance(xlim, list) else [xlim]
            ylim_list = ylim if isinstance(ylim, list) else [ylim]
            title_list = title if isinstance(title, list) else [title]
            xlabel_list = xlabel if isinstance(xlabel, list) else [xlabel]
            ylabel_list = ylabel if isinstance(ylabel, list) else [ylabel]
            
            # Ensure all lists have the same length
            num_plots = len(x_list)
            
            for i, test in enumerate(self.tests):
                for j in range(num_plots):
                    current_x = x_list[j]
                    current_y = y_list[j]
                    current_xlim = xlim_list[j]
                    current_ylim = ylim_list[j]
                    current_title = title_list[j]
                    current_xlabel = xlabel_list[j]
                    current_ylabel = ylabel_list[j]
                    is_final_page = (i == len(self.tests)-1) and (j == num_plots-1)
                    
                    # Check if the column names exist in the dataframe
                    if current_x not in test.data_process.columns:
                        print(f"Warning: Column '{current_x}' not found in data. Available columns: {test.data_process.columns.tolist()}")
                        continue
                    
                    if current_y not in test.data_process.columns:
                        print(f"Warning: Column '{current_y}' not found in data. Available columns: {test.data_process.columns.tolist()}")
                        continue
                    
                    fig_test, _ = test.plot_data(
                        x=current_x,
                        y=current_y,
                        xlim=current_xlim,
                        ylim=current_ylim,
                        title=current_title,
                        xlabel=current_xlabel,
                        ylabel=current_ylabel,
                        legend=[f'{sample_name} {test.get_sample_id()}'],
                        report_id=f"{self.repor_id['infle']}{self.repor_id['subinfle']}",
                        test_name=test_name,
                        num_pag=i*num_plots + j + num_1plot_pag,
                        final_pag=is_final_page
                        )
                    pdf_file.savefig(fig_test)
                plt.close()

    def make_report_file(self):
        return self.report_file

class Panel_toughness_test_report(Test_report):
    """
    Clase para generar informes de pruebas de tenacidad en paneles.

    Atributos:
        infle (str): Identificador de la prueba.
        subinfle (str): Subidentificador de la prueba.
        folder (str): Carpeta base donde se generan los archivos.
        standard (str): Norma aplicada en la prueba.
        client_id (str): Nombre de la empresa que realiza la prueba.
        samples_id (list): Identificadores de las muestras.
    """
    def __init__(self, infle=None, subinfle=None, folder=None, standard=None, client_id=None, samples_id=[]):
        super().__init__()
        self.repor_id = {'infle': infle, 'subinfle': subinfle}
        self.standard_test = standard
        self.folder_path = folder
        self.client_id = client_id
        self.samples_id = samples_id
        self.tests = []
        self.defl_points = np.array([])
        super().set_report_files()
    
    def set_defl_points(self):
        """Configura los puntos de deflexión según la norma."""
        standards_map = {
            'ASTMC1550': [5., 10., 20., 30., 40., 45.],
            'EFNARC1996': [5., 10., 15., 20., 25., 30.],
            'EFNARC1999': [5., 10., 15., 20., 25., 30.]
        }
        self.defl_points = np.array(standards_map[self.standard_test])
        if self.defl_points.size == 0:
            raise ValueError(f"Norma no reconocida: {self.standard_test}")
        return self.defl_points

    def add_tests(self):
        """Agrega pruebas basadas en los identificadores de muestras."""
        self.set_defl_points()

        for id in self.samples_id:
            test = Panels_toughness_test(sample_id=id, data_file=f'{self.folder_path}Losa P{id}.xlsx')
            test.get_data(data_file=test.data_file, data_source='xlsx', variable_names=['Time', 'Load', 'Deflection', 'Displacement'])
            test.preprocess_data(defl_points=self.defl_points)
            self.tests.append(test)

    def write_report(self):
        """Escribe los resultados en un archivo Excel."""
        for i, test in enumerate(self.tests):
            row_start = 5 * i + 18  # Posición inicial de la fila para cada prueba
            defl_cps = test.defl_cps
            for j, (deflection, load, toughness) in enumerate(zip(defl_cps['Deflection'], defl_cps['Load'], defl_cps['Toughness'])):
                column = 4 + j
                data = [load, deflection, toughness]
                for offset, value in enumerate(data):
                    write_data_excel(file_path=self.excel_file, sheet_name='Resultados', position=(row_start + offset, column), val=value)

    def make_report_file(self):
        self.add_tests()
        
        """Genera el archivo de informe final."""
        header_footer_pdf_path = f'./formatos/formato_no_acreditado.pdf'
        x='Deflection'
        y='Load'
        xlim=(0, self.defl_points[-1])
        ylim=(0, None)
        title='Fuerza-Deflexión'
        xlabel='Deflexión (mm)'
        ylabel='Fuerza (kN)'
        sample_name='PANEL'
        test_name='ENSAYO DE TENACIDAD POR FLEXIÓN'
        num_1plot_pag=4
        comparative=True
        x_comp='Deflection'
        y_comp='Toughness'
        xlim_comp=(0, self.defl_points[-1])
        ylim_comp=(0, None)
        title_comp='Energía-Deflexión'
        xlabel_comp='Deflexión (mm)'
        ylabel_comp='Energía (J)'       
        self.make_plot_report(
            x=x, y=y, xlim=xlim, ylim=ylim, title=title, xlabel=xlabel, ylabel=ylabel, sample_name=sample_name, test_name=test_name, num_1plot_pag=num_1plot_pag,
            comparative=comparative, x_comp=x_comp, y_comp=y_comp, xlim_comp=xlim_comp, ylim_comp=ylim_comp, title_comp=title_comp, xlabel_comp=xlabel_comp, ylabel_comp=ylabel_comp
            )
        
        self.write_report()
        convert_excel_to_pdf(excel_path=self.excel_file, pdf_path=self.report_file, pag_i=1, pag_f=num_1plot_pag-1)
        merge_pdfs(pdf_list=[self.report_file, self.plots_file], output_pdf=self.report_file)
        normalize_pdf_orientation(input_pdf_path=self.report_file, output_pdf_path=self.report_file, desired_orientation='portrait')
        apply_header_footer_pdf(input_pdf_path=self.report_file, header_footer_pdf_path=header_footer_pdf_path, output_pdf_path=self.report_file)

class Panel_Beam_residual_strength_test_report(Test_report):
    """
    Clase para generar informes de pruebas de tenacidad en paneles.

    Atributos:
        infle (str): Identificador de la prueba.
        subinfle (str): Subidentificador de la prueba.
        folder (str): Carpeta base donde se generan los archivos.
        standard (str): Norma aplicada en la prueba.
        client_id (str): Nombre de la empresa que realiza la prueba.
        samples_id (list): Identificadores de las muestras.
    """
    def __init__(self, infle=None, subinfle=None, folder=None, standard=None, client_id=None, samples_id=[]):
        super().__init__()
        self.repor_id = {'infle': infle, 'subinfle': subinfle}
        self.standard_test = standard
        self.folder_path = folder
        self.client_id = client_id
        self.samples_id = samples_id
        self.tests = []
        self.defl_points = np.array([])
        super().set_report_files()
    
    def set_defl_points(self):
        """Configura los puntos de deflexión según la norma."""
        standards_map = {
            'EN14651': [0.5, 1.5, 2.5, 3.5, 4.],
            'EN14488': [0.5, 1.5, 2.5, 3.5, 4., 5.]
        }
        self.defl_points = np.array(standards_map[self.standard_test])
        if self.defl_points.size == 0:
            raise ValueError(f"Norma no reconocida: {self.standard_test}")
        return self.defl_points

    def add_tests(self):
        """Agrega pruebas basadas en los identificadores de muestras."""
        self.set_defl_points()

        for id in self.samples_id:
            test = Beams_residual_strength_test(sample_id=id, data_file=f'{self.folder_path}{self.repor_id['infle']}-V-{id}/specimen.dat')
            test.get_data(data_file=test.data_file, data_source='csv', variable_names=['Time', 'Displacement', 'Load', 'CMOD', 'Deflection'])
            test.preprocess_data(defl_points=self.defl_points)
            self.tests.append(test)

    def write_report(self):
        """Escribe los resultados en un archivo Excel."""
        for i, test in enumerate(self.tests):
            row_start = i + 19  # Posición inicial de la fila para cada prueba
            defl_cps = test.defl_cps
            for j, (deflection, cmod, load, toughness) in enumerate(zip(defl_cps['Deflection'], defl_cps['CMOD'], defl_cps['Load'], defl_cps['Toughness'])):
                column = 20 + 4 * j
                data = [load, deflection, cmod, toughness]
                for offset, value in enumerate(data):
                    write_data_excel(file_path=self.excel_file, sheet_name='ResistenciaResidual', position=(row_start, column + offset), val=value)

    def make_report_file(self):
        self.add_tests()
        
        """Genera el archivo de informe final."""
        header_footer_pdf_path = f'./formatos/formato_no_acreditado.pdf'
        x=["Deflection", "CMOD"]
        y=["Load", "Load"]
        xlim=[(0, self.defl_points[-1]), (0, None)]
        ylim=[(0, None), (0, None)]
        title=["Fuerza-Deflexión", "Fuerza-CMOD"]
        xlabel=["Deflexión (mm)", "CMOD (mm)"]
        ylabel=["Fuerza (kN)", "Fuerza (kN)"]
        sample_name='VIGA'
        test_name='ENSAYO DE RESISTENCIA RESIDUAL EN FLEXIÓN'
        num_1plot_pag=5
        comparative=True
        x_comp='Deflection'
        y_comp='Toughness'
        xlim_comp=(0, self.defl_points[-1])
        ylim_comp=(0, None)
        title_comp='Energía-Deflexión'
        xlabel_comp='Deflexión (mm)'
        ylabel_comp='Energía (J)'       
        self.make_plot_report(
            x=x, y=y, xlim=xlim, ylim=ylim, title=title, xlabel=xlabel, ylabel=ylabel, sample_name=sample_name, test_name=test_name, num_1plot_pag=num_1plot_pag,
            comparative=comparative, x_comp=x_comp, y_comp=y_comp, xlim_comp=xlim_comp, ylim_comp=ylim_comp, title_comp=title_comp, xlabel_comp=xlabel_comp, ylabel_comp=ylabel_comp
            )
        
        self.write_report()
        convert_excel_to_pdf(excel_path=self.excel_file, pdf_path=self.report_file, pag_i=1, pag_f=num_1plot_pag-1)
        merge_pdfs(pdf_list=[self.report_file, self.plots_file], output_pdf=self.report_file)
        normalize_pdf_orientation(input_pdf_path=self.report_file, output_pdf_path=self.report_file, desired_orientation='portrait')
        apply_header_footer_pdf(input_pdf_path=self.report_file, header_footer_pdf_path=header_footer_pdf_path, output_pdf_path=self.report_file)

class Axial_compression_test_report(Test_report):
    """
    Clase para generar informes de pruebas de tenacidad en paneles.

    Atributos:
        infle (str): Identificador de la prueba.
        subinfle (str): Subidentificador de la prueba.
        folder (str): Carpeta base donde se generan los archivos.
        standard (str): Norma aplicada en la prueba.
        client_id (str): Nombre de la empresa que realiza la prueba.
        samples_id (list): Identificadores de las muestras.
    """
    def __init__(self, infle=None, subinfle=None, folder=None, standard=None, client_id=None, samples_id=[]):
        super().__init__()
        self.repor_id = {'infle': infle, 'subinfle': subinfle}
        self.standard_test = standard
        self.folder_path = folder
        self.client_id = client_id
        self.samples_id = samples_id
        self.tests = []
        self.defl_points = np.array([])
        super().set_report_files()

    def add_tests(self):
        for id in self.samples_id:
            test = Axial_compression_test(sample_id=id, data_file=f'{self.folder_path}{self.repor_id['infle']}-d{id}/specimen.dat')    #para data archivo tipo "csv"
            test.get_data(data_file=test.data_file, data_source='csv', variable_names=['Time', 'Displacement', 'Load'])                #para data archivo tipo "csv"
            #test = Axial_compression_test(sample_id=id, data_file=f'{self.folder_path}{self.repor_id['infle']}-d{id}/D{id}.xlsx')   #para data archivo tipo "excel"
            #test.get_data(data_file=test.data_file, data_source='xlsx', variable_names=['Time', 'Displacement', 'Load'])            #para data archivo tipo "excel"
            test.preprocess_data()
            self.tests.append(test)
    
    def write_report(self):
        for i, test in enumerate(self.tests):
            row = i+16
            column = 23
            write_data_excel(file_path=self.excel_file, sheet_name='Cores', position=(row, column), val=test.get_max_load())
            #column = 2
            #write_data_excel(file_path=self.report_file, sheet_idx=1, position=(row, column), val=test.get_area_section(cell=(1, 1)))
            #column = 3
            #write_data_excel(file_path=self.report_file, sheet_idx=1, position=(row, column), val=test.get_strength())
    
    def make_report_file(self):
        """Genera el archivo de informe final."""
        header_footer_pdf_path = f'./formatos/formato_acreditado.pdf'
        x='Displacement'
        y='Load'
        xlim=(0, None)
        ylim=(0, None)
        title='Fuerza-Desplazamiento'
        xlabel='Desplazamiento (mm)'
        ylabel='Fuerza (kN)'
        sample_name='CORE'
        test_name='ENSAYO DE RESISTENCIA A LA COMPRESIÓN'
        num_1plot_pag=4         #para cambiar la página de inicio de las gráficas
        comparative=False

        self.add_tests()
        self.write_report()
        convert_excel_to_pdf(excel_path=self.excel_file, pdf_path=self.report_file, pag_i=1, pag_f=num_1plot_pag-1)
        self.make_plot_report(
            x=x, y=y, xlim=xlim, ylim=ylim, title=title, xlabel=xlabel, ylabel=ylabel, sample_name=sample_name, test_name=test_name, num_1plot_pag=num_1plot_pag, final_pag=False,
            comparative=comparative
            )
        merge_pdfs(pdf_list=[self.report_file, self.plots_file], output_pdf=self.report_file)
        normalize_pdf_orientation(input_pdf_path=self.report_file, output_pdf_path=self.report_file, desired_orientation='portrait')
        apply_header_footer_pdf(input_pdf_path=self.report_file, header_footer_pdf_path=header_footer_pdf_path, output_pdf_path=self.report_file)

class Generate_test_report(Test_report):
    """
    Clase para generar informes de pruebas de tenacidad en paneles.

    Atributos:
        infle (str): Identificador de la prueba.
        subinfle (str): Subidentificador de la prueba.
        folder (str): Carpeta base donde se generan los archivos.
        standard (str): Norma aplicada en la prueba.
        client_id (str): Nombre de la empresa que realiza la prueba.
        samples_id (list): Identificadores de las muestras.
    """
    def __init__(self, infle=None, subinfle=None, folder=None, standard=None, client_id=None, samples_id=[]):
        super().__init__()
        self.repor_id = {'infle': infle, 'subinfle': subinfle}
        self.standard_test = standard
        self.folder_path = folder
        self.client_id = client_id
        self.samples_id = samples_id
        self.tests = []
        self.defl_points = np.array([])
        super().set_report_files(extension='xlsx')
    
    def make_report_file(self):
        """Genera el archivo de informe final."""
        header_footer_pdf_path = f'./formatos/formato_no_acreditado.pdf'

        convert_excel_to_pdf(excel_path=self.excel_file, pdf_path=self.report_file, pag_i=0, pag_f=0)
        #merge_pdfs(pdf_list=[self.report_file], output_pdf=self.report_file)
        normalize_pdf_orientation(input_pdf_path=self.report_file, output_pdf_path=self.report_file, desired_orientation='portrait')
        apply_header_footer_pdf(input_pdf_path=self.report_file, header_footer_pdf_path=header_footer_pdf_path, output_pdf_path=self.report_file)
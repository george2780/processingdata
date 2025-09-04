import os
from test_ledi import Panel_Beam_residual_strength_test_report

# Parámetros iniciales
infle = '111-25'
subinfle = '-C'
standar = 'EN14488'
empresa = 'PRODIMIN'
panels_id = [id+7 for id in range(3)]

# Directorios
base_dir = f'C:/Users/joela/Documents/MATLAB/Losas/{infle}/'
os.makedirs(base_dir, exist_ok=True)

# Crear el informe en excel
test_report = Panel_Beam_residual_strength_test_report(infle=infle, subinfle=subinfle, folder=base_dir, standard=standar, client_id=empresa, samples_id=panels_id)
test_report.make_report_file()

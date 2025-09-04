import os
from test_ledi import Panel_toughness_test_report

# Parámetros iniciales
infle = '117-25'
subinfle = '-A'
standar = 'EFNARC1996'
empresa = 'PRODIMIN'
panels_id = [id+1 for id in range(3)]    #Cambair 1 por 4, cuando se quiere hacer salto de panel

# Directorios
base_dir = f'E:/0_LEDI-PUCP/7_PANELES/{infle}/'   
os.makedirs(base_dir, exist_ok=True)

# Crear el informe en excel
test_report = Panel_toughness_test_report(infle=infle, subinfle=subinfle, folder=base_dir, standard=standar, client_id=empresa, samples_id=panels_id)
test_report.make_report_file()

import os
from test_ledi import Generate_test_report

# Parámetros iniciales
infle = '110-25'
subinfle = '-C'
standar = 'ABC'
empresa = 'PACASMAYO'

# Directorios
base_dir = f'E:/0_LEDI-PUCP/12_ALBAÑILERIA/2025 INF-LE 110-2025 - Ladrillo y Placas sílico calcáreas - PACASMAYO/{infle}/'
os.makedirs(base_dir, exist_ok=True)

# Crear el informe en excel
test_report = Generate_test_report(infle=infle, subinfle=subinfle, folder=base_dir, standard=standar, client_id=empresa)
test_report.make_report_file()

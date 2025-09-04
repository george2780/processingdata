import os
from test_ledi import Axial_compression_test_report

# Parámetros iniciales
infle = '159-25'
panel = 'P1'  #Cambiar a P2, P3, ... de acuerdo con cada panel
subinfle = '-A' 
standar = 'CORES'
empresa = 'MARSA'
cores_id = [id+1 for id in range(8)]    #Cambair 1 por 4, cuando se quiere hacer salto de panel

# Directorios
base_dir = f'E:/0_LEDI-PUCP/6_DIAMANTINAS/{infle}/{panel}/'
os.makedirs(base_dir, exist_ok=True)

# Crear el informe en excel
test_report = Axial_compression_test_report(infle=infle, subinfle=subinfle, folder=base_dir, standard=standar, client_id=empresa, samples_id=cores_id)
test_report.make_report_file()

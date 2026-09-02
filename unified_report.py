"""Script unificado para generar reportes de ensayos de diferentes tipos.

Este script puede generar reportes para múltiples tipos de ensayos mecánicos:
- cores: Ensayos de compresión axial (testigos de hormigón)
- cores_local: Compresión axial instrumentada con 3 strain gauges (curva esfuerzo-deformación)
- panels: Ensayos de tenacidad de paneles
- panels_residual: Ensayos de resistencia residual con CMOD (paneles/vigas, EN 14651 / EN 14488)
- beams_residual: Ensayos de resistencia residual de vigas por deflexión (ASTM C1609)
- tapas: Ensayos de flexión de tapas de buzón (tránsito)
- generic: Conversión genérica Excel -> PDF

Ejemplos de uso:
    # Reporte de testigos de hormigón
    python unified_report.py cores --infle 336-24 --subinfle S --standard CORES --empresa PRODIMIN --n 6

    # Reporte de testigos con strain gauges (esfuerzo-deformación)
    python unified_report.py cores_local --infle 336-24 --subinfle S --standard CORES --empresa PRODIMIN --n 3

    # Reporte de tenacidad de paneles
    python unified_report.py panels --infle 111-25 --subinfle C --standard EFNARC1996 --empresa PRODIMIN --n 3

    # Reporte de resistencia residual (CMOD)
    python unified_report.py panels_residual --infle 111-25 --subinfle C --standard EN14488 --empresa PRODIMIN --n 3

    # Reporte de resistencia residual de vigas (deflexión, ASTM C1609)
    python unified_report.py beams_residual --infle 222-25 --subinfle B --standard ASTMC1609 --empresa PRODIMIN --n 3

    # Reporte de flexión de tapas de buzón
    python unified_report.py tapas --infle 222-25 --subinfle A --standard NTP339.111 --empresa PRODIMIN --n 3

    # Conversión genérica
    python unified_report.py generic --infle 336-24 --subinfle S --standard DM --empresa EXC
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

from test_ledi import (
    Axial_compression_test_report,
    Axial_compression_local_test_report,
    Panel_toughness_test_report,
    Panel_Beam_residual_strength_test_report,
    Beam_residual_strength_test_report,
    Tapa_buzon_flexion_test_report,
    Generate_test_report,
    Test_report
)
from report_helpers import prepare_output_dir, run_report


# Configuración de tipos de ensayo
REPORT_CONFIGS = {
    'cores': {
        'report_class': Axial_compression_test_report,
        'description': 'Genera reporte de ensayos de compresión axial (testigos)',
        'default_standard': 'CORES',
        'standard_choices': None,
        'default_client': 'PRODIMIN',
        'default_base': 'G:/0_LEDI-PUCP/6_DIAMANTINAS',
        'default_n': 6,
        'requires_samples': True,
    },
    'cores_local': {
        'report_class': Axial_compression_local_test_report,
        'description': 'Genera reporte de compresión axial con strain gauges (curva esfuerzo-deformación)',
        'default_standard': 'CORES',
        'standard_choices': None,
        'default_client': 'PRODIMIN',
        'default_base': 'D:/',
        'default_n': 3,
        'requires_samples': True,
    },
    'panels': {
        'report_class': Panel_toughness_test_report,
        'description': 'Genera reporte de ensayos de tenacidad de paneles',
        'default_standard': 'EFNARC1996',
        'standard_choices': list(Panel_toughness_test_report._standards_map.keys()),
        'default_client': 'PRODIMIN',
        'default_base': 'D:/',
        'default_n': 3,
        'requires_samples': True,
    },
    'panels_residual': {
        'report_class': Panel_Beam_residual_strength_test_report,
        'description': 'Genera reporte de ensayos de resistencia residual con CMOD (EN 14651 / EN 14488)',
        'default_standard': 'EN14488',
        'standard_choices': list(Panel_Beam_residual_strength_test_report._standards_map.keys()),
        'default_client': 'PRODIMIN',
        'default_base': 'D:/',
        'default_n': 3,
        'requires_samples': True,
    },
    'beams_residual': {
        'report_class': Beam_residual_strength_test_report,
        'description': 'Genera reporte de ensayos de resistencia residual de vigas por deflexión (ASTM C1609)',
        'default_standard': 'ASTMC1609',
        'standard_choices': list(Beam_residual_strength_test_report._standards_map.keys()),
        'default_client': 'PRODIMIN',
        'default_base': 'D:/',
        'default_n': 3,
        'requires_samples': True,
    },
    'tapas': {
        'report_class': Tapa_buzon_flexion_test_report,
        'description': 'Genera reporte de ensayos de flexión de tapas de buzón (tránsito)',
        'default_standard': 'Tapa_Circular_CA',
        'standard_choices': None,
        'default_client': 'PRODIMIN',
        'default_base': 'D:/',
        'default_n': 3,
        'requires_samples': True,
    },
    'generic': {
        'report_class': Generate_test_report,
        'description': 'Genera reporte genérico (sólo conversión Excel -> PDF)',
        'default_standard': 'GENERIC',
        'standard_choices': None,
        'default_client': 'EMPRESA',
        'default_base': 'D:/',
        'default_n': 0,
        'requires_samples': False,
    },
}


# Archivo de configuración opcional por informe. Se busca dentro de la carpeta
# {base-dir}/{infle}/ (o donde indique --config). Permite fijar una sola vez los
# parámetros que describen la plantilla y los datos de ese informe, en lugar de
# repetir flags en cada corrida. Precedencia: flag CLI > config > default de clase.
CONFIG_FILENAME = 'report_config.json'
CONFIG_KEYS = {'start_row', 'num_1plot_pag', 'file_pattern', 'columns'}


def load_report_config(folder: str, config_path: Optional[str] = None) -> Dict:
    """Carga el JSON de configuración del informe, si existe.

    Args:
        folder: Carpeta del informe ({base-dir}/{infle}/) donde se busca
            ``CONFIG_FILENAME`` por defecto.
        config_path: Ruta explícita (--config). Si se da y no existe, es error;
            si no se da y el archivo por defecto no existe, devuelve {}.

    Returns:
        Dict sólo con las claves reconocidas (``CONFIG_KEYS``).
    """
    path = Path(config_path) if config_path else Path(folder) / CONFIG_FILENAME
    if not path.exists():
        if config_path:
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"El archivo de configuración debe ser un objeto JSON: {path}")
    unknown = set(data) - CONFIG_KEYS
    if unknown:
        logging.warning(
            f"Claves no reconocidas en {path}: {sorted(unknown)} (se ignoran). "
            f"Válidas: {sorted(CONFIG_KEYS)}"
        )
    cfg = {k: v for k, v in data.items() if k in CONFIG_KEYS}
    if cfg:
        logging.info(f"Configuración cargada de {path}: {cfg}")
    return cfg


def setup_logging(verbose: bool = False) -> None:
    """Configura el sistema de logging."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def build_samples_id(n: int, offset: int = 1) -> List[int]:
    """Construye lista de IDs de muestras consecutivos.
    
    Args:
        n: Número de muestras
        offset: Valor inicial (por defecto 1)
        
    Returns:
        Lista de IDs de muestras
    """
    if n <= 0:
        return []
    return [offset + i for i in range(n)]


def get_samples_id(args: argparse.Namespace) -> List[int]:
    """Obtiene lista de IDs de muestras desde argumentos.
    
    Args:
        args: Argumentos parseados
        
    Returns:
        Lista de IDs de muestras
    """
    config = REPORT_CONFIGS[args.test_type]
    
    if not config['requires_samples']:
        return []
    
    # Si se especificaron IDs directamente
    if hasattr(args, 'ids') and args.ids is not None:
        return args.ids
    
    # Si se especificó número de muestras
    if hasattr(args, 'n') and args.n is not None:
        return build_samples_id(args.n, args.offset)
    
    # Usar valores por defecto
    return build_samples_id(config['default_n'], args.offset)


def parse_arguments() -> argparse.Namespace:
    """Parsea argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description='Script unificado para generar reportes de ensayos mecánicos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Subcomandos para tipos de ensayo
    subparsers = parser.add_subparsers(
        dest='test_type',
        help='Tipo de ensayo/reporte a generar',
        required=True
    )
    
    # Crear subparser para cada tipo de ensayo
    for test_type, config in REPORT_CONFIGS.items():
        subparser = subparsers.add_parser(
            test_type,
            help=config['description']
        )
        
        # Argumentos comunes
        subparser.add_argument(
            '--infle',
            required=True,
            help='Identificador del informe (ej: 336-24)'
        )
        
        subparser.add_argument(
            '--subinfle',
            default='',
            help='Sub-identificador del informe (ej: S, C)'
        )
        
        subparser.add_argument(
            '--standard',
            default=config['default_standard'],
            choices=config['standard_choices'],
            help=f'Estándar del ensayo (por defecto: {config["default_standard"]})'
        )
        
        subparser.add_argument(
            '--empresa',
            default=config['default_client'],
            help=f'Nombre de la empresa cliente (por defecto: {config["default_client"]})'
        )
        
        subparser.add_argument(
            '--base-dir',
            default=config['default_base'],
            help=f'Directorio base (por defecto: {config["default_base"]})'
        )
        
        if config['requires_samples']:
            # Grupo mutuamente exclusivo para especificar muestras
            sample_group = subparser.add_mutually_exclusive_group()

            sample_group.add_argument(
                '--n',
                type=int,
                default=config['default_n'],
                help=f'Número de muestras consecutivas (por defecto: {config["default_n"]})'
            )

            sample_group.add_argument(
                '--ids',
                type=int,
                nargs='+',
                help='IDs específicos de muestras (ej: --ids 3 4 7)'
            )

            subparser.add_argument(
                '--offset',
                type=int,
                default=1,
                help='Valor inicial para IDs de muestras cuando se usa --n (por defecto: 1)'
            )

            default_num_1plot_pag = getattr(config['report_class'], 'num_1plot_pag', None)
            subparser.add_argument(
                '--num-1plot-pag',
                dest='num_1plot_pag',
                type=int,
                default=None,
                help=(
                    'Número de página donde inician los gráficos en el informe '
                    f'(por defecto: {default_num_1plot_pag}). Controla el rango '
                    'de páginas exportadas desde Excel: pag_f = num_1plot_pag - 1.'
                )
            )

            default_start_row = getattr(config['report_class'], 'start_row', None)
            subparser.add_argument(
                '--start-row',
                dest='start_row',
                type=int,
                default=None,
                help=(
                    'Fila de la plantilla Excel correspondiente a la primera '
                    f'muestra, para lectura y escritura (por defecto: {default_start_row}). '
                    'Las muestras siguientes ocupan filas consecutivas o bloques '
                    'según el layout del ensayo.'
                )
            )

            default_pattern = getattr(config['report_class'], 'data_file_pattern', None)
            subparser.add_argument(
                '--file-pattern',
                dest='file_pattern',
                default=None,
                help=(
                    'Patrón del nombre del archivo de datos por muestra, relativo a '
                    '{base-dir}/{infle}/. Marcadores: {id} (obligatorio), {infle}, {subinfle}. '
                    'La extensión decide el lector: .xlsx/.xlsm/.xls como Excel, el resto '
                    'como texto delimitado. Ej: "Panel M{id}.xlsx" '
                    f'(por defecto: {default_pattern or "automático"}).'
                )
            )

            default_columns = list(getattr(config['report_class'], 'data_columns', ()) or ())
            subparser.add_argument(
                '--columns',
                dest='columns',
                nargs='+',
                default=None,
                help=(
                    'Nombres de las columnas del archivo de datos, en el orden en que '
                    'aparecen en el archivo. Ej: --columns Time Deflection Load Displacement '
                    f'(por defecto: {" ".join(default_columns) or "según el ensayo"}).'
                )
            )

            subparser.add_argument(
                '--config',
                dest='config',
                default=None,
                help=(
                    f'Ruta a un JSON de configuración del informe. Si se omite, se busca '
                    f'{CONFIG_FILENAME} en {{base-dir}}/{{infle}}/. Claves: '
                    f'{", ".join(sorted(CONFIG_KEYS))}. Los flags del CLI tienen prioridad.'
                )
            )

        subparser.add_argument(
            '--verbose',
            '-v',
            action='store_true',
            help='Habilita salida verbose'
        )
    
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """Valida argumentos de entrada.
    
    Args:
        args: Argumentos parseados
        
    Raises:
        ValueError: Si hay argumentos inválidos
    """
    config = REPORT_CONFIGS[args.test_type]
    
    # Validar directorio base
    base_path = Path(args.base_dir)
    if not base_path.exists():
        logging.warning(f"El directorio base {base_path} no existe, se creará automáticamente")
    
    if config['requires_samples']:
        # Validar IDs específicos si se proporcionaron
        if hasattr(args, 'ids') and args.ids is not None:
            if any(id_val <= 0 for id_val in args.ids):
                raise ValueError(f"Todos los IDs de muestras deben ser > 0, recibidos: {args.ids}")
        
        # Validar número de muestras si se proporcionó
        elif hasattr(args, 'n') and args.n is not None:
            if args.n < 0:
                raise ValueError(f"El número de muestras debe ser >= 0, recibido: {args.n}")
        
        # Validar offset
        if hasattr(args, 'offset') and args.offset < 0:
            raise ValueError(f"El offset debe ser >= 0, recibido: {args.offset}")

        # Validar fila inicial de la plantilla
        start_row = getattr(args, 'start_row', None)
        if start_row is not None and start_row < 1:
            raise ValueError(f"La fila inicial (--start-row) debe ser >= 1, recibida: {start_row}")
    
    logging.info(f"Argumentos validados para tipo de ensayo: {args.test_type}")


def generate_report(args: argparse.Namespace) -> None:
    """Genera el reporte basado en los argumentos.
    
    Args:
        args: Argumentos parseados y validados
    """
    config = REPORT_CONFIGS[args.test_type]
    report_class = config['report_class']
    
    # Preparar directorio de salida
    folder = prepare_output_dir(args.base_dir, args.infle)
    
    # Preparar lista de muestras
    samples_id = get_samples_id(args)
    if config['requires_samples']:
        logging.info(f"Generando reporte para {len(samples_id)} muestras: {samples_id}")
    else:
        logging.info("Generando reporte genérico (sin muestras específicas)")
    
    # Ejecutar generación del reporte
    report_kwargs = dict(
        infle=args.infle,
        subinfle=args.subinfle,
        folder=folder,
        standard=args.standard,
        client_id=args.empresa,
        samples_id=samples_id,
    )
    # Parámetros de layout/datos: flag CLI > report_config.json > default de clase.
    file_config = load_report_config(folder, getattr(args, 'config', None)) if config['requires_samples'] else {}

    def resolve_param(name):
        cli_value = getattr(args, name, None)
        return cli_value if cli_value is not None else file_config.get(name)

    num_1plot_pag = resolve_param('num_1plot_pag')
    if num_1plot_pag is not None:
        report_kwargs['num_1plot_pag'] = int(num_1plot_pag)
    start_row = resolve_param('start_row')
    if start_row is not None:
        report_kwargs['start_row'] = int(start_row)
    file_pattern = resolve_param('file_pattern')
    if file_pattern is not None:
        report_kwargs['data_file_pattern'] = str(file_pattern)
    columns = resolve_param('columns')
    if columns is not None:
        if not isinstance(columns, (list, tuple)) or not all(isinstance(c, str) for c in columns):
            raise ValueError(f"'columns' debe ser una lista de nombres de columna: {columns!r}")
        report_kwargs['data_columns'] = list(columns)

    try:
        run_report(report_class, **report_kwargs)
        logging.info(f"Reporte generado exitosamente en: {folder}")
        
    except Exception as e:
        logging.error(f"Error al generar el reporte: {e}")
        raise


def main() -> None:
    """Función principal del script."""
    try:
        # Parsear argumentos
        args = parse_arguments()
        
        # Configurar logging
        setup_logging(args.verbose)
        
        logging.info(f"Iniciando generación de reporte tipo: {args.test_type}")
        logging.debug(f"Argumentos recibidos: {vars(args)}")
        
        # Validar argumentos
        validate_arguments(args)
        
        # Generar reporte
        generate_report(args)
        
        logging.info("Proceso completado exitosamente")
        
    except KeyboardInterrupt:
        logging.warning("Proceso interrumpido por el usuario")
        sys.exit(1)
        
    except Exception as e:
        logging.error(f"Error en el proceso: {e}")
        if hasattr(args, 'verbose') and args.verbose:
            logging.exception("Detalles del error:")
        sys.exit(1)


if __name__ == '__main__':  # pragma: no cover
    main()

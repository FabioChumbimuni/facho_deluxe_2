"""
Sistema de Pollers Zabbix - Reemplazo del Coordinador

Este módulo implementa un sistema de ejecución de tareas estilo Zabbix:
- Scheduler que identifica nodos listos cada 1 segundo
- Poller Manager que gestiona múltiples pollers paralelos
- Protección OLT (1 nodo a la vez por OLT)
- Nodos encadenados tratados como unidad (1 nodo compuesto)
"""

default_app_config = 'zabbix_pollers.apps.ZabbixPollersConfig'


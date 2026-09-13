# Transitorio: reexporta los servicios hasta que las vistas importen por modulo.
from .alquileres import (CATEGORIAS_GASTO_CASA, FILTROS_ALQUILERES, Q_COBRADA, Q_LIBRE, Q_PENDIENTE,
                         crear_casa, crear_contrato, crear_gasto_casa, editar_casa, editar_contrato,
                         editar_gasto_casa, eliminar_casa, eliminar_contrato, eliminar_gasto_casa,
                         marcar_pago_alquiler, obtener_casa, obtener_casas,
                         obtener_contrato_de_casa, obtener_datos_casa, obtener_detalle_alquiler,
                         obtener_resumen_alquileres)
from .alquileres import (_contrato_en_dict, _validar_casa, _validar_contrato, _validar_gasto_casa,
                         _validar_plazo_libre)
from .cereales import (crear_gasto_viaje_cereal, crear_viaje_cereal, editar_viaje_cereal,
                       eliminar_viaje_cereal, marcar_pago_viaje_cereal, obtener_datos_viaje_cereal,
                       obtener_resumen_cereal, obtener_viajes_cereal_de_cliente,
                       obtener_viajes_cereales)
from .cereales import _validar_viaje_cereal
from .cheques import (MAX_IMPORTE_CHEQUE, crear_banco, crear_cheque, crear_cuenta_corriente,
                      editar_banco, editar_cheque, editar_cuenta_corriente, eliminar_banco,
                      eliminar_cheque, eliminar_cuenta_corriente, marcar_cobrado_cheque,
                      obtener_bancos_activos, obtener_cheques, obtener_cuentas_corrientes,
                      obtener_datos_banco, obtener_datos_cheque, obtener_datos_cuenta_corriente,
                      obtener_empresas_con_cheques, obtener_empresas_para_selector_cheques,
                      obtener_totales_cheques)
from .cheques import (_validar_cheque, _validar_nombre_banco, _validar_numero_cheque,
                      _validar_numero_cuenta)
from .clientes import (ORDEN_MOVIMIENTO, buscar_clientes, editar_cliente, eliminar_cliente,
                       nuevo_cliente, obtener_datos_cliente, obtener_movimientos_cuenta_corriente,
                       obtener_saldo_anterior_cuenta_corriente)
from .clientes import _items_operacion
from .combustible import (alternar_pago_carga, crear_carga, crear_estacion, editar_carga,
                          editar_estacion, eliminar_carga, eliminar_estacion, obtener_cargas,
                          obtener_datos_carga, obtener_datos_estacion, obtener_estaciones_activas,
                          obtener_totales_cargas)
from .combustible import _validar_carga
from .comunes import (MAX_COSTO, MAX_KILOMETROS, REGEX_CTG, REGEX_FACTURA, REGEX_PATENTE,
                      REGEX_TEXTO_BASICO, REGEX_TEXTO_NUMEROS, filtro_nombre_apellido,
                      filtro_tokens, mes_desplazado, resolver_periodo)
from .comunes import (_acotar_rango, _aplicar_estado_pago, _decimal_opcional, _entero_opcional,
                      _fecha_obligatoria, _guardar_unico, _iniciales, _momento_local, _parsear_dia,
                      _parsear_periodo, _texto_opcional)
from .cotizaciones import (CATEGORIAS_INICIO, actualizar_cotizacion, get_cotizacion_cera_operculo,
                           get_cotizacion_dolar_oficial, get_cotizacion_miel_50mm,
                           get_tablero_inicio)
from .cotizaciones import _grupo_inicio
from .deudores import obtener_listado_deudores
from .empleados import (crear_empleado, crear_pago_empleado, desplazar_periodo_pagos,
                        editar_empleado, editar_pago_empleado, eliminar_empleado,
                        eliminar_pago_empleado, etiqueta_periodo_pagos, fijar_sueldo_empleado,
                        fijar_vencimiento_carnet, obtener_cuenta_corriente, obtener_datos_empleado,
                        obtener_empleados_activos, rango_periodo_pagos, resolver_ancla_pagos)
from .empleados import (_lunes_de, _movimientos_cuenta_corriente, _normalizar_datos_pago,
                        _presentar_saldo, _saldo_arrastre)
from .filtros import (incluir_asignado, nombre_cliente_operaciones_filtro,
                      nombre_destino_reparto_filtro, nombre_empleado_filtro,
                      nombre_producto_operaciones_filtro, nombre_vehiculo_filtro,
                      opciones_clientes_operaciones, opciones_destinos_cereal,
                      opciones_destinos_reparto_filtro, opciones_destinos_viaje,
                      opciones_empleados_filtro, opciones_productos_operaciones,
                      opciones_vehiculos_filtro)
from .filtros import _opciones_destinos_texto
from .flota import (crear_observacion, crear_registro_km, crear_seguro, crear_servis,
                    crear_vehiculo, crear_vtv, editar_observacion, editar_registro_km,
                    editar_seguro, editar_servis, editar_vehiculo, editar_vtv, eliminar_observacion,
                    eliminar_registro_km, eliminar_seguro, eliminar_servis, eliminar_vehiculo,
                    eliminar_vtv, obtener_observaciones, obtener_registros_km, obtener_seguros,
                    obtener_servicios, obtener_vehiculos_activos, obtener_vtvs)
from .flota import _validar_kilometraje, _validar_observacion, _validar_servis, _validar_vigencia
from .iva import (MAX_MONTO_IVA, crear_empresa, crear_operacion_iva, editar_empresa,
                  editar_operacion_iva, eliminar_empresa, eliminar_operacion_iva,
                  obtener_datos_empresa, obtener_datos_operacion_iva, obtener_empresas_activas,
                  obtener_operaciones_iva, obtener_totales_iva)
from .iva import (_validar_alicuota, _validar_nombre_empresa, _validar_operacion_iva,
                  _validar_tipo_operacion)
from .marcos import (MAX_MARCOS, crear_marco, editar_marco, eliminar_marco,
                     nombre_cliente_marcos_filtro, obtener_datos_marco, obtener_marcos,
                     opciones_clientes_marcos)
from .marcos import _validar_marco
from .operaciones import (crear_operacion, editar_operacion, obtener_operaciones_listado,
                          servicio_cancelar_operacion)
from .operaciones import (_aplicar_items, _limpiar_observaciones, _parsear_cotizaciones_historicas,
                          _parsear_fecha_operacion, _procesar_item_granel, _revertir_stock_detalles,
                          _validar_items_congelados)
from .productos import (editar_producto, editar_producto_por_kg, eliminar_producto,
                        eliminar_producto_por_kg, modificar_stock, modificar_stock_por_kg,
                        nuevo_producto, nuevo_producto_por_kg, obtener_datos_producto,
                        obtener_datos_producto_por_kg)
from .productos import _a_kilos, _validar_producto_por_kg
from .reparto import (crear_destino_reparto, crear_gasto_viaje_reparto, crear_viaje_reparto,
                      editar_destino_reparto, editar_viaje_reparto, eliminar_destino_reparto,
                      eliminar_viaje_reparto, marcar_pago_viaje_reparto,
                      obtener_datos_viaje_reparto, obtener_destinos_reparto,
                      obtener_resumen_reparto, obtener_viajes_reparto)
from .reparto import (_limpiar_valor_viaje, _restar_viaje_a_destino, _sumar_viaje_a_destino,
                      _validar_destino_reparto, _validar_viaje_reparto)
from .viajes import (crear_gasto, crear_ingreso_caja, crear_viaje, editar_gasto_viaje,
                     editar_ingreso_caja, editar_viaje, eliminar_gasto_viaje, eliminar_ingreso_caja,
                     eliminar_viaje, obtener_datos_viaje, obtener_viajes, registrar_devolucion_caja)
from .viajes import (_CONFIG_CARGA_GASTO, _limpiar_devolucion, _sincronizar_carga_combustible,
                     _validar_gasto_viaje, _validar_monto_devuelto, _validar_monto_ingreso,
                     _validar_viaje)

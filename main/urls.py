from django.urls import path
from main.views import (login, inicio, actualizar_cotizacion_ajax,
                        productos, clientes, informacion_clientes, informacion_operacion, generar_remito,
                        nueva_operacion_venta, nueva_operacion_compra, cancelar_operacion, registrar_pago, obtener_cliente_json,
                        obtener_producto_json, obtener_producto_por_kg_json, viajes, operaciones, informacion_viaje, deudores, cerrar_sesion, flota,
                        informacion_vehiculo,
                        viaje_cereales, informacion_viaje_cereal, buscar_clientes_json,
                        combustible, marcar_pago_cereal_ajax,
                        empleados, obtener_empleado_json, informacion_empleado,
                        generar_resumen_cuenta, contar_movimientos_cuenta_json,
                        obtener_estacion_json,
                        informacion_estacion, obtener_carga_json)

"""
La sentencia name="nombre_del_archivo" se usa 
para que Django sepa la ruta relativa del .html
"""
"""
Viajes repartos (con su catalogo de Destinos), Alquileres, Cheques e IVA quedan
fuera del sistema: sin path() no hay URL que resuelva, asi que Django contesta
404 y nada delata que esas pantallas existen. Un permiso habria contestado 403,
que es justamente lo que confirmaria que estan ahi.

Las vistas siguen en views.py y sus plantillas en su lugar: para reponerlas
alcanza con devolver los path() y sumar sus vistas al import de arriba.
"""
urlpatterns = [
    path('', login, name="login"),
    path('inicio/', inicio, name="inicio"),
    path('actualizar_cotizacion/', actualizar_cotizacion_ajax, name="actualizar_cotizacion"),
    path('productos/', productos, name="productos"),
    path('clientes/', clientes, name="clientes"),
    path('empleados/', empleados, name="empleados"),
    path('informacion_empleado/<int:id_empleado>/', informacion_empleado, name="informacion_empleado"),
    path('informacion_clientes/<int:id_cliente>/', informacion_clientes, name="informacion_clientes"),
    path('informacion_operacion/<int:id_operacion>/', informacion_operacion, name="informacion_operacion"),
    path('generar_remito/<int:id_operacion>/', generar_remito, name="generar_remito"),
    path('resumen_cuenta/<int:id_cliente>/', generar_resumen_cuenta, name="generar_resumen_cuenta"),
    path('api/clientes/<int:id_cliente>/movimientos/', contar_movimientos_cuenta_json,
         name="contar_movimientos_cuenta"),
    path('cancelar_operacion/<int:id_operacion>/', cancelar_operacion, name="cancelar_operacion"),
    path('registrar_pago/<int:id_operacion>/', registrar_pago, name="registrar_pago"),
    path('nueva_operacion_venta/<int:id_cliente>/', nueva_operacion_venta, name="nueva_operacion_venta"),
    path('nueva_operacion_compra/<int:id_cliente>/', nueva_operacion_compra, name="nueva_operacion_compra"),
    path('api/clientes/buscar/', buscar_clientes_json, name="buscar_clientes_json"),
    path('api/clientes/<int:id_cliente>/', obtener_cliente_json, name="obtener_cliente_json"),
    path('api/productos/<int:id_producto>/', obtener_producto_json, name="obtener_producto_json"),
    path('api/productos_por_kg/<int:id_producto>/', obtener_producto_por_kg_json, name="obtener_producto_por_kg_json"),
    path('api/empleados/<int:id_empleado>/', obtener_empleado_json, name="obtener_empleado_json"),
    path('viajes/', viajes, name="viajes"),
    path('operaciones/', operaciones, name="operaciones"),
    path('flota/', flota, name="flota"),
    path('informacion_vehiculo/<int:id_vehiculo>/', informacion_vehiculo, name="informacion_vehiculo"),
    path('informacion_viaje/<int:id_viaje>/', informacion_viaje, name="informacion_viaje"),
    path('deudores/', deudores, name="deudores"),
    path('combustible/', combustible, name="combustible"),
    path('api/estaciones/<int:id_estacion>/', obtener_estacion_json, name="obtener_estacion_json"),
    path('informacion_estacion/<int:id_estacion>/', informacion_estacion, name="informacion_estacion"),
    path('api/cargas/<int:id_carga>/', obtener_carga_json, name="obtener_carga_json"),
    path('viajes_cereales/', viaje_cereales, name="viajes_cereales"),
    path('informacion_viaje_cereal/<int:id_viaje_cereal>/', informacion_viaje_cereal, name="informacion_viaje_cereal"),
    path('api/viajes_cereales/<int:id_viaje_cereal>/pagado/', marcar_pago_cereal_ajax, name="marcar_pago_cereal"),
    path('cerrar_sesion', cerrar_sesion, name="cerrar_sesion")
]
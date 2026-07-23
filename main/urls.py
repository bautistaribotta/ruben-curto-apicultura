from django.urls import path
from main.views import (login, inicio, actualizar_cotizacion_ajax,
                        productos, clientes, informacion_clientes, informacion_operacion, generar_remito,
                        nueva_operacion_venta, nueva_operacion_compra, cancelar_operacion, registrar_pago, obtener_cliente_json,
                        obtener_producto_json, viajes, informacion_viaje, deudores, mercado_libre, cerrar_sesion, flota,
                        viaje_cereales, informacion_viaje_cereal, informacion_viaje_reparto, buscar_clientes_json,
                        alquileres, combustible, marcar_pago_reparto_ajax, marcar_pago_cereal_ajax,
                        destinos_reparto, empleados, obtener_empleado_json, informacion_empleado)

"""
La sentencia name="nombre_del_archivo" se usa 
para que Django sepa la ruta relativa del .html
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
    path('cancelar_operacion/<int:id_operacion>/', cancelar_operacion, name="cancelar_operacion"),
    path('registrar_pago/<int:id_operacion>/', registrar_pago, name="registrar_pago"),
    path('nueva_operacion_venta/<int:id_cliente>/', nueva_operacion_venta, name="nueva_operacion_venta"),
    path('nueva_operacion_compra/<int:id_cliente>/', nueva_operacion_compra, name="nueva_operacion_compra"),
    path('api/clientes/buscar/', buscar_clientes_json, name="buscar_clientes_json"),
    path('api/clientes/<int:id_cliente>/', obtener_cliente_json, name="obtener_cliente_json"),
    path('api/productos/<int:id_producto>/', obtener_producto_json, name="obtener_producto_json"),
    path('api/empleados/<int:id_empleado>/', obtener_empleado_json, name="obtener_empleado_json"),
    path('viajes/', viajes, name="viajes"),
    path('flota/', flota, name="flota"),
    path('informacion_viaje/<int:id_viaje>/', informacion_viaje, name="informacion_viaje"),
    path('deudores/', deudores, name="deudores"),
    path('alquileres/', alquileres, name="alquileres"),
    path('combustible/', combustible, name="combustible"),
    path('mercado_libre/', mercado_libre, name="mercado_libre"),
    path('destinos_reparto/', destinos_reparto, name="destinos_reparto"),
    path('informacion_viaje_reparto/<int:id_viaje_reparto>/', informacion_viaje_reparto, name="informacion_viaje_reparto"),
    path('api/viajes_reparto/<int:id_viaje_reparto>/pagado/', marcar_pago_reparto_ajax, name="marcar_pago_reparto"),
    path('viajes_cereales/', viaje_cereales, name="viajes_cereales"),
    path('informacion_viaje_cereal/<int:id_viaje_cereal>/', informacion_viaje_cereal, name="informacion_viaje_cereal"),
    path('api/viajes_cereales/<int:id_viaje_cereal>/pagado/', marcar_pago_cereal_ajax, name="marcar_pago_cereal"),
    path('cerrar_sesion', cerrar_sesion, name="cerrar_sesion")
]
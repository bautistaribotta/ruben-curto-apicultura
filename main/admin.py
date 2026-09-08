from django.contrib import admin
from .models import (
    Cliente, Producto, Operacion, DetalleOperacion, Pago, ProductoPorKg,
    Empleado, PagosEmpleados, Vehiculo, Viaje, DetalleViaje, Gasto,
    ViajeReparto, DetalleViajeReparto, DestinoViajeReparto, ViajeCereal, DetalleViajeCereal,
    GastoViajeCereal, Casa, Contrato, PagoAlquiler, GastoCasa, EstacionDeServicio,
    RegistroKilometraje, Seguro, VTV, Servis, ObservacionVehiculo,
    Empresa, OperacionIva,
    Banco, CuentaCorriente, Cheque,
)

admin.site.register(Cliente)
admin.site.register(Pago)


"""
Productos: la unica pantalla donde se decide que sale en el tablero de inicio.
El flag no esta en el panel del inventario a proposito, es una decision de
configuracion de cada instalacion y no del usuario que carga productos, asi que
se maneja desde aca con la lista editable.
"""


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'categoria', 'precio', 'cantidad', 'mostrar_en_inicio', 'activo')
    list_editable = ('mostrar_en_inicio',)
    list_filter = ('mostrar_en_inicio', 'categoria', 'activo')
    search_fields = ('nombre',)


@admin.register(ProductoPorKg)
class ProductoPorKgAdmin(admin.ModelAdmin):
    list_display = ('id', 'articulo', 'categoria', 'monto', 'cantidad', 'mostrar_en_inicio', 'activo')
    list_editable = ('mostrar_en_inicio',)
    list_filter = ('mostrar_en_inicio', 'categoria', 'activo')
    search_fields = ('articulo',)


admin.site.register(Empleado)
admin.site.register(PagosEmpleados)


class RegistroKilometrajeInline(admin.TabularInline):
    model = RegistroKilometraje
    extra = 1

class SeguroInline(admin.TabularInline):
    model = Seguro
    extra = 1

class VTVInline(admin.TabularInline):
    model = VTV
    extra = 1

class ServisInline(admin.TabularInline):
    model = Servis
    extra = 1

class ObservacionVehiculoInline(admin.TabularInline):
    model = ObservacionVehiculo
    extra = 1

@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    inlines = [RegistroKilometrajeInline, SeguroInline, VTVInline, ServisInline, ObservacionVehiculoInline]
    list_display = ('id', 'nombre', 'patente', 'kilometraje_actual', 'ultima_actualizacion_km', 'activo')
    search_fields = ('nombre', 'patente')

@admin.register(RegistroKilometraje)
class RegistroKilometrajeAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehiculo', 'fecha', 'kilometros')
    list_filter = ('vehiculo',)

@admin.register(Seguro)
class SeguroAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehiculo', 'inicio', 'fin', 'costo', 'vencido')
    list_filter = ('vehiculo',)

@admin.register(VTV)
class VTVAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehiculo', 'inicio', 'fin', 'costo', 'vencido')
    list_filter = ('vehiculo',)

@admin.register(Servis)
class ServisAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehiculo', 'fecha', 'costo')
    list_filter = ('vehiculo',)

@admin.register(ObservacionVehiculo)
class ObservacionVehiculoAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehiculo', 'fecha', 'texto')
    list_filter = ('vehiculo',)

class DetalleOperacionInline(admin.TabularInline):
    model = DetalleOperacion
    extra = 1

@admin.register(Operacion)
class OperacionAdmin(admin.ModelAdmin):
    inlines = [DetalleOperacionInline]

class DetalleViajeInline(admin.TabularInline):
    model = DetalleViaje
    extra = 1

class GastoInline(admin.TabularInline):
    model = Gasto
    extra = 1

@admin.register(Viaje)
class ViajeAdmin(admin.ModelAdmin):
    inlines = [DetalleViajeInline, GastoInline]
    list_display = ('id', 'empleado', 'vehiculo', 'fecha_inicio', 'fecha_vuelta')

@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ('id', 'viaje', 'gasto', 'monto', 'fecha')

class DetalleViajeRepartoInline(admin.TabularInline):
    model = DetalleViajeReparto
    extra = 1

@admin.register(ViajeReparto)
class ViajeRepartoAdmin(admin.ModelAdmin):
    inlines = [DetalleViajeRepartoInline]
    list_display = ('id', 'fecha_viaje_reparto', 'empleado', 'vehiculo', 'destino', 'valor_viaje', 'activo')

@admin.register(DestinoViajeReparto)
class DestinoViajeRepartoAdmin(admin.ModelAdmin):
    list_display = ('id', 'localidad_destino', 'valor_viaje', 'cant_viajes', 'activo')

class DetalleViajeCerealInline(admin.TabularInline):
    model = DetalleViajeCereal
    extra = 1

class GastoViajeCerealInline(admin.TabularInline):
    model = GastoViajeCereal
    extra = 1

@admin.register(ViajeCereal)
class ViajeCerealAdmin(admin.ModelAdmin):
    inlines = [DetalleViajeCerealInline, GastoViajeCerealInline]
    list_display = ('id', 'fecha_viaje_cereal', 'cliente', 'empleado', 'vehiculo', 'tipo_cereal', 'toneladas', 'activo')

@admin.register(GastoViajeCereal)
class GastoViajeCerealAdmin(admin.ModelAdmin):
    list_display = ('id', 'viaje_cereal', 'gasto', 'monto', 'fecha')

class PagoAlquilerInline(admin.TabularInline):
    model = PagoAlquiler
    extra = 1

class ContratoInline(admin.TabularInline):
    model = Contrato
    extra = 1

class GastoCasaInline(admin.TabularInline):
    model = GastoCasa
    extra = 1

@admin.register(Casa)
class CasaAdmin(admin.ModelAdmin):
    inlines = [ContratoInline, PagoAlquilerInline, GastoCasaInline]
    list_display = ('id', 'nombre', 'localidad', 'direccion', 'activa')

@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ('id', 'casa', 'inicio', 'fin', 'monto_mensual', 'comision_inmobiliaria', 'nombre_inquilino')
    list_filter = ('casa',)

@admin.register(PagoAlquiler)
class PagoAlquilerAdmin(admin.ModelAdmin):
    list_display = ('id', 'casa', 'periodo', 'fecha', 'monto')

@admin.register(GastoCasa)
class GastoCasaAdmin(admin.ModelAdmin):
    list_display = ('id', 'casa', 'fecha', 'categoria', 'detalle', 'monto')
    list_filter = ('categoria', 'casa')

@admin.register(EstacionDeServicio)
class EstacionDeServicioAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)


class OperacionIvaInline(admin.TabularInline):
    model = OperacionIva
    extra = 1

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    inlines = [OperacionIvaInline]
    list_display = ('id', 'nombre', 'iva_debito', 'iva_credito', 'saldo_iva', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)

@admin.register(OperacionIva)
class OperacionIvaAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'tipo', 'fecha', 'monto_neto', 'alicuota', 'iva')
    list_filter = ('tipo', 'empresa')


class CuentaCorrienteInline(admin.TabularInline):
    model = CuentaCorriente
    extra = 1


@admin.register(Banco)
class BancoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre',)


class ChequeInline(admin.TabularInline):
    model = Cheque
    extra = 1


@admin.register(CuentaCorriente)
class CuentaCorrienteAdmin(admin.ModelAdmin):
    inlines = [ChequeInline]
    list_display = ('id', 'empresa', 'banco', 'numero', 'cheques_a_pagar', 'activa')
    list_filter = ('activa', 'banco', 'empresa')
    search_fields = ('numero',)


@admin.register(Cheque)
class ChequeAdmin(admin.ModelAdmin):
    list_display = ('id', 'cuenta_corriente', 'fecha_emision', 'fecha_cobro', 'importe', 'vencido')
    list_filter = ('cuenta_corriente__banco', 'cuenta_corriente__empresa')

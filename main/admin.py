from django.contrib import admin
from .models import (
    Cliente, Producto, Operacion, DetalleOperacion, Pago, Cotizaciones,
    Empleado, PagosEmpleados, Vehiculo, Viaje, DetalleViaje, Gasto,
    ViajeReparto, DetalleViajeReparto, DestinoViajeReparto, ViajeCereal, DetalleViajeCereal,
    GastoViajeCereal, Casa, PagoAlquiler,
)

admin.site.register(Cliente)
admin.site.register(Producto)
admin.site.register(Pago)
admin.site.register(Cotizaciones)
admin.site.register(Empleado)
admin.site.register(PagosEmpleados)
admin.site.register(Vehiculo)

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

@admin.register(Casa)
class CasaAdmin(admin.ModelAdmin):
    inlines = [PagoAlquilerInline]
    list_display = ('id', 'nombre', 'localidad', 'direccion', 'precio', 'comision_inmobiliaria', 'alquilada', 'activa')

@admin.register(PagoAlquiler)
class PagoAlquilerAdmin(admin.ModelAdmin):
    list_display = ('id', 'casa', 'periodo', 'fecha', 'monto')

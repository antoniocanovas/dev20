# Gimnasio: venta de bonos de clases y reservas online (Odoo 20)

Investigación del 20/10/2026. **Solo investigación, nada desarrollado ni probado en base.**
Todo verificado leyendo el código de `20odoo`, `20enterprise` y `20industry`.

## Punto de partida

Partimos de la **parametrización del módulo de industria `yoga_pilates`** (`20industry/yoga_pilates`).

Comparativa de los módulos de industria revisados:

| Módulo | Bono de clases | Reserva online con pago | Encaje |
|---|---|---|---|
| **yoga_pilates** | ✅ "5-Class Yoga & Pilates Card" (tarjeta de fidelización) | ✅ Citas con aforo, recurso, horario y producto | **Base elegida** |
| sports_club | `loyalty` instalado, sin bono montado | Citas sin pago ni venta | Parcial |
| fitness | No | Citas y eventos, sin bono | Parcial |
| members_club | No (suscripciones y eventos) | Solo eventos | No |
| event_management | No (organización de eventos para clientes) | No | No |
| personal_trainer | No | Citas en backend, sin web | No |

(`sport_club` y `personal_training` no existen; son `sports_club` y `personal_trainer`.)

### Cómo funciona yoga_pilates

1. **Bono**: producto "5-Class Card" ligado a un programa `loyalty` que da 5 puntos al comprarlo (`demo/loyalty_rule.xml`).
2. **Clases**: tipos de cita con aforo, recurso (sala), horario semanal, producto "Single Yoga Class" y paso de pago (`data/appointment_type.xml`). `min_cancellation_hours = 2`.
3. **Consumo**: al pagar la reserva se canjea 1 punto = 100 % de descuento sobre la clase (`demo/loyalty_reward.xml`). Sin puntos, se paga el precio normal.
4. **Alternativa**: membresías con suscripción y lista de precios a 0 € en las clases incluidas.

## Lo que ofrece de serie

- **Saldo del bono en el portal** (`/my`): tarjeta en la columna lateral con el saldo y el historial de movimientos (`loyalty/views/portal_templates.xml:2`, `loyalty/controllers/portal.py:43`).
  - Requisitos: programa de tipo `loyalty`/`ewallet`, activo, sin caducar, cliente con usuario de portal y "Visible en el portal" marcado (ya viene así en yoga_pilates).
  - Ajuste recomendado: cambiar `portal_point_name` a "clase(s)".
- **Reservas en el portal** (`/my/appointments`, `appointment/controllers/portal.py:45`): filtros Próximas/Pasadas/Todas. El filtro por defecto es "Todas"; se puede enlazar a `/my/appointments?filterby=upcoming`. Las canceladas no salen (se archivan).
- Bono y reservas aparecen en sitios distintos del portal; no hay vista conjunta.

## Problema: devoluciones o cancelaciones de reservas

- **El cliente no puede cancelar desde la web una reserva con pago**, aunque la pagara con el bono: `_get_prevent_cancel_status` devuelve `no_cancel_paid` si el tipo de cita tiene `has_payment_step` (`20enterprise/appointment_account_payment/controllers/calendar.py:6`). El mismo método bloquea también **reprogramar** (`appointment/controllers/calendar.py:121` y `:147`).
- **Desde el backend sí funciona**: cancelar el pedido de venta archiva la cita, liberando la plaza (`website_appointment_sale/models/sale_order.py:31`), y borra el historial de puntos del pedido, devolviendo el punto al bono (`sale_loyalty/models/sale_order.py:266`, saldo calculado desde `loyalty.history`).
- El dinero de una clase pagada con tarjeta se reembolsa a mano.

Datos verificados útiles:
- Estado "Cancelled" de la cita ⇔ cita archivada (`appointment/models/calendar_event.py:426-437`).
- `base_automation` de la 20 tiene el disparador `on_archive` ("On archived").
- `sale.order.action_cancel()` es público y cancela directamente, sin asistente (`sale/models/sale_order.py:1791`). Solo falla si el pedido está bloqueado.
- Ajuste de puntos con método público: `loyalty.card.update.balance` y `action_update_card_point()` (`loyalty/wizard/loyalty_card_update_balance.py:16`). Da error si el nuevo saldo es negativo.

## Opciones estudiadas

### A. Studio y reglas automatizadas, manteniendo el pago en la cita

Regla sobre *Evento de calendario* con el disparador "On archived", que cancela el pedido de las reservas pagadas con el bono:

```python
lines = env['sale.order.line'].search([('calendar_event_id', '=', record.id)])
orders = lines.order_id.filtered(lambda o: o.state == 'sale' and o.amount_total == 0)
orders.action_cancel()
```

- ✅ Recepción cancela y el punto vuelve solo. Se puede añadir la comprobación del plazo.
- ✅ Solicitud de cancelación por parte del cliente: editar el texto del aviso `no_cancel_paid` (es una plantilla web, `appointment_account_payment/views/appointment_templates_validation.xml:5`) para enlazar a un formulario; recepción la valida. No automatizarla: un formulario público no verifica la identidad.
- ❌ El cliente no puede cancelar por sí mismo desde la web.

### B. Módulo pequeño que quite `no_cancel_paid`

- Sobrescribir `_get_prevent_cancel_status`: si la reserva se pagó con el bono (pedido a 0 €), aplicar solo el plazo (`super` de `appointment`); en cualquier otro caso, mantener `no_cancel_paid`. Mantener **reprogramar bloqueado**.
- Cancelar desde la web solo archiva la cita (`action_cancel_meeting`), así que hace falta cancelar además el pedido. Puede hacerlo la regla de la opción A o el propio módulo.
- Esfuerzo bajo (menos de un día con pruebas). Riesgo bajo: el método está pensado para extenderse.

### C. Solo reservas con bono, sin pago en la cita

- Tipos de cita con `has_payment_step = False`, así que no hay pedido ni `no_cancel_paid`. La cancelación por parte del cliente dentro del plazo funciona de serie.
- Reglas automatizadas con Python:
  - Al crear la cita: descontar 1 punto con `loyalty.card.update.balance`; si no tiene saldo, lanzar un error.
  - "On archived": devolver 1 punto.
- Problemas:
  1. **Identidad (el más grave)**: la reserva es pública (`/appointment/<id>/submit`, `auth="public"`, `appointment/controllers/appointment.py:614`). Sin iniciar sesión, al cliente se le identifica por el email del formulario, así que cualquiera podría gastar el bono de otro. Sin desarrollo no se puede obligar a iniciar sesión.
  2. Reprogramar crea la cita nueva antes de archivar la antigua: si al cliente le queda 0, falla.
  3. Reservas para varias personas (`asked_capacity`): descontar ese número.
  4. "No show" no archiva, así que la clase se pierde (probablemente es lo que se quiere).
  5. Si el cliente tiene varias tarjetas, hay que decidir de cuál se descuenta.
  6. El error por falta de saldo aparece al final del formulario (mala experiencia). No se pueden ocultar los huecos a quien no tiene bono.
  7. No permite vender clases sueltas pagadas con tarjeta (habría que venderlas como bono de 1).

| | A/B: pago en la cita con canje | C: solo bono |
|---|---|---|
| El cliente cancela desde la web | ❌ (✅ con el módulo B) | ✅ de serie |
| Descontar y devolver clases | ✅ de serie al cancelar el pedido | Reglas con Python |
| Clases sueltas con tarjeta | ✅ | ❌ |
| Identifica al cliente | Sí, vía pago | Solo un email |
| Sin saldo | Paga el precio normal | Error al final del formulario |

## Pendiente al retomar

- [ ] Decidir la opción: A (sin módulo, cancelación por recepción), B (módulo pequeño) o C (solo bonos, con riesgo de identidad).
- [ ] Instalar `yoga_pilates` en una base de prueba de la 20 y comprobar el flujo real.
- [ ] **Sin verificar**: en una clase con aforo, comprobar que cada reserva crea su propia cita. Si varias reservas comparten una, archivarla afectaría a todos los asistentes.
- [ ] Probar los casos: cancelar en plazo, cancelar fuera de plazo, reserva pagada con dinero, clase con varios asistentes, reprogramar.

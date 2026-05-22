# Panel de Control

El Panel de Control es la primera pantalla que ve después de iniciar sesión. Proporciona una **visión rápida** del estado general de toda la arquitectura empresarial.

![Panel de Control - Vista superior](../assets/img/es/01_panel_de_control.png)

## Barra de Navegación Superior

En la parte superior de la pantalla encontrará la **barra de navegación principal** con los siguientes elementos:

- **Turbo EA** (logo): Haga clic para volver al Panel de Control desde cualquier sección
- **Panel de control**: Vista general del estado de la arquitectura
- **Inventario**: Listado completo de todas las fichas
- **Informes**: Informes visuales y analíticos
- **BPM**: Gestión de Procesos de Negocio (si está habilitado)
- **Diagramas**: Editor visual de diagramas de arquitectura
- **Entrega EA**: Gestión de iniciativas de arquitectura
- **Tareas**: Tareas pendientes y encuestas asignadas
- **Buscar fichas**: Barra de búsqueda rápida con autocompletado
- **+ Crear**: Botón para crear nuevas fichas rápidamente
- **Campana de notificaciones**: Alertas del sistema y [notificaciones](notifications.es.md)
- **Icono de perfil**: Selección de idioma, cambio de tema, preferencias de notificaciones y acceso a administración

## Tarjetas de Resumen

La sección principal del Panel de Control muestra **tarjetas de resumen** que indican:

- **Número total de fichas**: Cantidad total de componentes registrados en la plataforma
- **Distribución por tipo**: Cuántos elementos de cada tipo existen (Aplicaciones, Organizaciones, Objetivos, Capacidades, etc.)
- **Vista general de estado**: Visualizaciones rápidas del estado general

Al hacer clic en una tarjeta de tipo, se navega al [Inventario](inventory.es.md) pre-filtrado por ese tipo.

![Panel de Control - Vista inferior con gráficos](../assets/img/es/02_panel_inferior.png)

## Gráficos y Estadísticas

En la parte inferior del Panel de Control encontrará:

- **Gráfico de distribución por tipo**: Muestra la proporción de cada tipo de ficha en su panorama
- **Estado de aprobación**: Indica cuántas fichas están aprobadas, pendientes, rotas o rechazadas
- **Calidad de datos**: Porcentaje general de completitud de la información en todas las fichas
- **Actividad reciente**: Un historial de los últimos cambios — quién editó qué y cuándo

## Pestaña «Espacio de trabajo»

La pestaña **Espacio de trabajo** reúne todo lo que se le ha asignado: favoritos, tareas, encuestas pendientes, actividad reciente en sus tarjetas y la sección **Tarjetas en las que tengo un rol**.

Esta última agrupa las tarjetas por el rol de parte interesada que ejerce (Application Owner, Business Owner, etc.) y lista las tarjetas bajo cada rol. Si su rol concede el permiso `stakeholders.view` (admin, member y viewer de forma predeterminada), aparece un pequeño icono **person_search** junto al título de la sección: elija un usuario en el autocompletado y la sección se recarga con sus roles y tarjetas. El título cambia a «Roles de {name}». Pulse el pequeño icono de cierre para volver a sus propios roles. Útil para responder a «¿qué posee esta persona?» con un clic.

## Pestaña «Administración» — Directorio de partes interesadas

Los administradores (cualquier rol con `admin.users`) ven un widget **Directorio de partes interesadas** en la parte inferior de la pestaña Administración. Enumera cada tipo de tarjeta con al menos una parte interesada, junto con el número de titulares distintos. Expanda un tipo de tarjeta para ver sus roles, y dentro de cada rol los usuarios con el número de tarjetas que cubren. Es la respuesta a nivel de organización a «¿quién es responsable de qué?», en una sola pantalla y un clic por tipo de tarjeta.

Las chips del widget son **sensibles al hover**: detenga el cursor sobre cualquier chip de usuario en el directorio — o sobre el nombre de una parte interesada en la pestaña Partes interesadas de una tarjeta, o sobre un propietario de riesgo en el Registro de riesgos o en la página de Detalle del riesgo — y se abrirá un pequeño popover con la cartera completa de esa persona agrupada por rol. Haga clic en cualquier tarjeta del popover para saltar a ella. El popover solo realiza la búsqueda una vez por usuario por sesión.

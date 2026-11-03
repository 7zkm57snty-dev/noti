# CEV NOTICIAS — Panel administrativo

Worker privado para `admin.cevnoticias.com`, integrado con el repositorio `7zkm57snty-dev/noti`.

## Arquitectura y seguridad

- Cloudflare Access autentica la solicitud antes de que el Worker entregue el panel o procese la API. El Worker vuelve a comprobar `ctx.access` y la identidad.
- La interfaz se importa como módulo de texto mediante Wrangler. No se usa el router de Static Assets, para conservar el contexto de Access en el Worker.
- El token de GitHub solo se lee desde el secreto `GITHUB_TOKEN` del Worker. Nunca se devuelve al navegador.
- Las altas, ediciones y retiros crean una rama `revision-admin/*` y una propuesta contra `main`.
- Aprobar fusiona la propuesta y el panel espera a que el workflow de GitHub Pages termine. Antes de marcar la actualización como completada, el workflow consulta el dominio público sin caché y compara portada, titular, resumen, cuerpo y fotografía con cache.json. Rechazar cierra la propuesta.
- Se mantiene `cache.json` como fuente de datos y se conservan los procesos de publicación actuales.
- El workflow automático ahora se pausa tanto ante propuestas automáticas como ante propuestas creadas desde el panel.

## Conectar el Worker existente a GitHub

En Cloudflare:

1. Workers & Pages → `cev-admin` → Settings → Builds → Connect.
2. Autoriza Cloudflare GitHub App y elige `7zkm57snty-dev/noti`.
3. Production branch: `main`.
4. Root directory: `admin-worker`.
5. Build command: dejar vacío.
6. Deploy command: `npx wrangler deploy`.
7. Guarda la conexión. El nombre en Cloudflare debe seguir siendo `cev-admin`.

Cloudflare Workers Builds permite conectar un Worker existente desde Settings → Builds. Al conectarlo, los commits en la rama configurada activan las implementaciones.

## Crear el secreto GITHUB_TOKEN

En GitHub crea un Fine-grained personal access token:
- Resource owner: tu cuenta de GitHub.
- Repository access: Only select repositories → `noti`.
- Repository permissions:
  - Metadata: Read-only.
  - Contents: Read and write.
  - Pull requests: Read and write.

En Cloudflare → Workers & Pages → `cev-admin` → Settings → Variables and Secrets:
1. En Production, elige Add variable.
2. Selecciona tipo Secret.
3. Nombre: `GITHUB_TOKEN`.
4. Pega el token directamente en Cloudflare y guarda.
5. No lo pegues en GitHub, no lo añadas a archivos y no lo compartas en el chat.

El token habilita lectura de `cache.json`, creación de ramas y pull requests, cierre y fusión de propuestas. Limítalo al repositorio de CEV NOTICIAS y establece una expiración razonable.

## Probar

Después de que Cloudflare despliegue la versión y el secreto exista, abre `https://admin.cevnoticias.com` e inicia sesión con el método autorizado por Cloudflare Access.

## Funciones de esta entrega

- Resumen con indicadores.
- Cola de revisión editorial.
- Crear artículos.
- Editar y solicitar retiro de artículos.
- Buscar y filtrar noticias.
- Aprobar o rechazar propuestas.
- Validaciones de titular, resumen, categoría, 250 palabras, enlaces HTTPS, doble fuente para temas sensibles y atribución completa de fotografías.

## Funciones posteriores

- WhatsApp: pendiente de activar un proveedor y guardar su API key como secreto.
- Notificaciones web/push: pendiente de implementar y probar.
- El panel confirma la fusión de una propuesta y el inicio del despliegue, pero no afirma que el sitio esté actualizado hasta que GitHub Actions termine correctamente.

## Registro de despliegue

Se registra este cambio documental para activar la primera compilación automática de Cloudflare desde la rama `main`, con el directorio raíz `admin-worker`.


## Verificación de publicación pública

`verificar_publicacion.py` compara las páginas servidas por el dominio configurado en GitHub Pages con los artículos de `cache.json`. Se ejecuta después de `deploy-pages`, usa peticiones HTTP sin caché y reintenta durante varios minutos para dar margen a la propagación. Si el dominio sigue sirviendo texto anterior, falta una fotografía o una noticia retirada continúa visible, el workflow falla y el panel no anuncia que la web ya está actualizada.

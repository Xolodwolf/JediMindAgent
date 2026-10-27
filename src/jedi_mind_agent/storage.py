from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """Hashed static file names, so browsers can cache them forever and never keep an old version after a deploy.

    `support_js_module_import_aggregation` makes collectstatic rewrite `import … from "./x.js"` in the web
    interface's ES modules to the hashed names as well.
    """

    support_js_module_import_aggregation = True

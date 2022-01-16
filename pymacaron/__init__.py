import os
import sys
import logging
import click
import pkg_resources
import inspect
from uuid import uuid4
from flask import Response, redirect
from flask_compress import Compress
from flask_cors import CORS
from pymacaron_core.swagger.apipool import ApiPool
from pymacaron_core.models import get_model
import pymacaron.models
from pymacaron.apiloader import load_api_models_and_endpoints
from pymacaron.log import set_level, pymlogger
from pymacaron.crash import set_error_reporter, generate_crash_handler_decorator
from pymacaron.exceptions import format_error
from pymacaron.config import get_config
from pymacaron.monitor import monitor_init
from pymacaron.api import add_ping_hook


log = pymlogger(__name__)


# TODO: deprecate
def _get_model_factory(model_name):
    # Using dynamic method creation to localize model_name
    def factory(**kwargs):
        return get_model(model_name)(**kwargs)
    return factory


class apispecs():
    """Keep track of the path of the openapi spec file of every loaded api"""

    __api_name_to_path = {}

    @classmethod
    def register_api_path(cls, api_name, api_path):
        """Remember where to find the openapi file of this api"""
        apispecs.__api_name_to_path[api_name] = api_path

    @classmethod
    def get_api_path(cls, api_name):
        """Get the path of the openapi file of this api, or None if that api has not been loaded"""
        return apispecs.__api_name_to_path.get(api_name, None)


class modelpool():
    """The modelpool of an api is a class whose attributes are all the Pymacaron
    model classes declared in that api
    """

    def __init__(self, name):
        self.api_name = name

    def __getattr__(self, model_name):
        raise Exception(f'Either {self.api_name}.yaml has not been loaded or it does not define object {model_name}')

    def json_to_model(self, model_name, j, keep_datetime=None):
        """Given a model name and json dict, return an instantiated pymacaron object"""
        # TODO: keep_datetime in this method should be deprecated...
        assert keep_datetime is not False, "Support for keep_datetime=False not implemented"
        return getattr(self, model_name).from_json(j)


class apipool():
    """The apipool contains the modelpools of all loaded apis"""

    @classmethod
    def add_model(cls, api_name, model_name, model_class):
        """Register a model class defined in an api"""
        # Set modelpool.<model_name> to model_class. This allows writing:
        #   from pymacaron import apipool
        #   o = apipool.ping.Ok()
        if not hasattr(apipool, api_name):
            setattr(apipool, api_name, modelpool(api_name))
        models = getattr(apipool, api_name)
        setattr(models, model_name, model_class)

    @classmethod
    def get_model(cls, api_name):
        """Return the pymacaron modelpool for this api"""
        assert hasattr(apipool, api_name), f"Api {api_name} is not loaded in apipool"
        return getattr(apipool, api_name)

    @classmethod
    def load_swagger(cls, api_name, api_path, dest_dir=None, load_endpoints=True, force=False):
        """Load a swagger/openapi specification into pymacaron: generate its model
        classes (declared with pydantic), and optionally generate the Flask api
        endpoints binding endpoint methods to routes.

        Syntax:
            apipool.load_swagger('ping', '../apis/ping.yaml')

        api_name : str
            Name of the api, used to access api models.
        api_path : str
            Path of the swagger file of the api.
        dest_dir: str
            Optional. Path to a directory under which to write the generated
            '<api_name>_models.py' and '<api_name>_app.py' files. Defaults to
            the same directory as the swagger file.
        load_endpoints: bool
            Optional. Set to false to only generate model declarations, and not
            endpoint declarations. Defaults to true.
        force: bool
            Optional. Force regenerating the model and endpoint code even if
            the code files are up to date with the swagger file. Defaults to
            false.

        """

        app_pkg = load_api_models_and_endpoints(
            api_name=api_name,
            api_path=api_path,
            dest_dir=dest_dir,
            load_endpoints=load_endpoints,
            force=force,
        )

        apispecs.register_api_path(api_name, api_path)

        return app_pkg


def get_port():
    """Find which TCP port to listen to, based on environment variables"""
    if 'PORT' in os.environ:
        port = os.environ['PORT']
        log.info("Environment variable PORT is set: will listen on port %s" % port)
    elif 'PYM_SERVER_PORT' in os.environ:
        port = os.environ['PYM_SERVER_PORT']
        log.info("Environment variable PYM_SERVER_PORT is set: will listen on port %s" % port)
    else:
        port = 80
        log.info("No HTTP port specified. Will listen on port 80")

    return port



#
# API: class to define then run a micro service api
#

class API(object):


    def __init__(self, app, host='localhost', port=None, debug=False, log_level=logging.DEBUG, formats=None, timeout=20, error_reporter=None, default_user_id=None, error_callback=format_error, error_decorator=None, ping_hook=[]):
        """

        Configure the Pymacaron microservice prior to starting it. Arguments:

        - app: the flask app
        - port: (optional) the http port to listen on (defaults to 80)
        - debug: (optional) whether to run with flask's debug mode (defaults to False)
        - error_reporter: (optional) a callback to call when catching exceptions, for custom reporting to slack, email or whatever
        - log_level: (optional) the microservice's log level (defaults to logging.DEBUG)
        - ping_hook: (optional) a function to call each time Amazon calls the ping endpoint, which happens every few seconds

        """
        assert app
        assert port

        self.app = app
        self.port = port
        self.host = host
        self.debug = debug
        self.formats = formats
        self.timeout = timeout
        self.error_callback = error_callback
        self.error_decorator = error_decorator
        self.ping_hook = ping_hook

        if not port:
            self.port = get_port()

        if default_user_id:
            self.default_user_id = default_user_id

        set_level(log_level)

        if error_reporter:
            set_error_reporter(error_reporter)

        log.info("Initialized API (%s:%s) (Flask debug:%s)" % (host, port, debug))


    def publish_apis(self, path='doc'):
        """Publish all loaded apis on under the uri /<path>/<api-name>, by
        redirecting to http://petstore.swagger.io/
        """

        # TODO: refactor publish_apis to use apispecs

        assert path

        if not self.apis:
            raise Exception("You must call .load_apis() before .publish_apis()")

        # Infer the live host url from pym-config.yaml
        proto = 'http'
        if hasattr(get_config(), 'aws_cert_arn'):
            proto = 'https'

        live_host = "%s://%s" % (proto, get_config().live_host)

        # Allow cross-origin calls
        CORS(self.app, resources={r"/%s/*" % path: {"origins": "*"}})

        # Add routes to serve api specs and redirect to petstore ui for each one
        for api_name, api_path in self.apis.items():

            api_filename = os.path.basename(api_path)
            log.info("Publishing api %s at /%s/%s" % (api_name, path, api_name))

            def redirect_to_petstore(live_host, api_filename):
                def f():
                    url = 'http://petstore.swagger.io/?url=%s/%s/%s' % (live_host, path, api_filename)
                    log.info("Redirecting to %s" % url)
                    return redirect(url, code=302)
                return f

            def serve_api_spec(api_path):
                def f():
                    with open(api_path, 'r') as f:
                        spec = f.read()
                        log.info("Serving %s" % api_path)
                        return Response(spec, mimetype='text/plain')
                return f

            self.app.add_url_rule('/%s/%s' % (path, api_name), str(uuid4()), redirect_to_petstore(live_host, api_filename))
            self.app.add_url_rule('/%s/%s' % (path, api_filename), str(uuid4()), serve_api_spec(api_path))

        return self


    def load_builtin_apis(self, names=['ping']):
        """Load some or all of the builtin apis 'ping' and 'crash'"""
        for name in names:
            yaml_path = pkg_resources.resource_filename(__name__, 'pymacaron/%s.yaml' % name)
            if not os.path.isfile(yaml_path):
                yaml_path = os.path.join(os.path.dirname(sys.modules[__name__].__file__), '%s.yaml' % name)
            apipool.load_swagger(
                name,
                yaml_path,
                dest_dir=get_config().apis_path,
                load_endpoints=True,
            )


    def load_clients(self, path=None, apis=[]):
        """Generate client libraries for the given apis, without starting an
        api server"""

        if not path:
            raise Exception("Missing path to api swagger files")

        if type(apis) is not list:
            raise Exception("'apis' should be a list of api names")

        if len(apis) == 0:
            raise Exception("'apis' is an empty list - Expected at least one api name")

        for api_name in apis:
            api_path = os.path.join(path, '%s.yaml' % api_name)
            if not os.path.isfile(api_path):
                raise Exception("Cannot find swagger specification at %s" % api_path)
            apipool.load_swagger(
                api_name,
                api_path,
                dest_dir=path,
                load_endpoints=False,
                # timeout=self.timeout,
                # error_callback=self.error_callback,
                # formats=self.formats,
                # local=False,
            )

        return self


    def load_apis(self, path, ignore=[]):
        """Load all swagger files found at the given path, except those whose
        names are in the 'ignore' list"""

        path = get_config().apis_path

        if type(ignore) is not list:
            raise Exception("'ignore' should be a list of api names")

        # Always ignore pym-config.yaml
        ignore.append('pym-config')

        # Find all swagger apis under 'path'
        apis = {}

        log.debug("Searching path %s" % path)
        for root, dirs, files in os.walk(path):
            for f in files:
                if f.startswith('.#') or f.startswith('#'):
                    log.info("Ignoring file %s" % f)
                elif f.endswith('.yaml'):
                    api_name = f.replace('.yaml', '')

                    if api_name in ignore:
                        log.info("Ignoring api %s" % api_name)
                        continue

                    apis[api_name] = os.path.join(path, f)
                    log.debug("Found api %s in %s" % (api_name, f))

        # Save found apis
        self.path_apis = path
        self.apis = apis

        return self


    def start(self, serve=[]):
        """Load all apis, either as local apis served by the flask app, or as
        remote apis to be called from whithin the app's endpoints, then start
        the app server"""

        # Check arguments
        if type(serve) is str:
            serve = [serve]
        elif type(serve) is list:
            pass
        else:
            raise Exception("'serve' should be an api name or a list of api names")

        if len(serve) == 0:
            raise Exception("You must specify at least one api to serve")

        for api_name in serve:
            if api_name not in self.apis:
                raise Exception("Can't find %s.yaml (swagger file) in the api directory %s" % (api_name, self.path_apis))

        app = self.app
        app.secret_key = os.urandom(24)

        # Initialize JWT config
        conf = get_config()
        if hasattr(conf, 'jwt_secret'):
            log.info("Set JWT parameters to issuer=%s audience=%s secret=%s***" % (
                conf.jwt_issuer,
                conf.jwt_audience,
                conf.jwt_secret[0:8],
            ))

        # Always serve the ping api
        serve.append('ping')

        # Add ping hooks if any
        if self.ping_hook:
            add_ping_hook(self.ping_hook)

        self.load_builtin_apis()

        # Let's compress returned data when possible
        compress = Compress()
        compress.init_app(app)

        # Now load those apis into the ApiPool
        for api_name, api_path in self.apis.items():
            app_pkg = apipool.load_swagger(
                api_name,
                api_path,
                dest_dir=os.path.dirname(api_path),
                load_endpoints=True if api_name in serve else False,
                # TODO: support timeout, error_callback, formats, host/port
                # timeout=self.timeout,
                # error_callback=self.error_callback,
                # formats=self.formats,
                # local=False,
                # host=host,
                # port=port,
            )
            log.info(f"[{app_pkg}] for {api_name}")
            if app_pkg:
                app_pkg.load_endpoints(app)

        log.debug("Argv is [%s]" % '  '.join(sys.argv))
        if 'celery' in sys.argv[0].lower():
            # This code is loading in a celery worker - Don't start the actual flask app.
            log.info("Running in a Celery worker - Not starting the Flask app")
            return

        # Initialize monitoring, if any is defined
        monitor_init(app=app, config=conf)

        if os.path.basename(sys.argv[0]) == 'gunicorn':
            # Gunicorn takes care of spawning workers
            log.info("Running in Gunicorn - Not starting the Flask app")
            return

        # Debug mode is the default when not running via gunicorn
        app.debug = self.debug

        app.run(host='0.0.0.0', port=self.port)

#
# Generic code to start server, from command line or via gunicorn
#


def show_splash():
    log.info("")
    log.info("")
    log.info("")
    log.info("       _ __  _   _ _ __ ___   __ _  ___ __ _ _ __ ___  _ __ ")
    log.info("      | '_ \| | | | '_ ` _ \ / _` |/ __/ _` | '__/ _ \| '_ \ ")
    log.info("      | |_) | |_| | | | | | | (_| | (_| (_| | | | (_) | | | |")
    log.info("      | .__/ \__, |_| |_| |_|\__,_|\___\__,_|_|  \___/|_| |_|")
    log.info("      | |     __/ |")
    log.info("      |_|    |___/")
    log.info("")
    log.info("       microservices made easy    -     http://pymacaron.com")
    log.info("")
    log.info("")
    log.info("")


def letsgo(name, callback=None):
    assert callback

    @click.command()
    @click.option('--port', help="Set server listening port (default: 80)", default=None)
    @click.option('--env', help="Set the environment, hence forcing to run against live, staging or dev by setting the PYM_ENV variable", default=None)
    @click.option('--debug/--no-debug', default=True)
    def main(port, env, debug):

        if env:
            log.info("Overriding PYM_ENV to '%s'" % env)
            os.environ['PYM_ENV'] = env

        conf = get_config()

        show_splash()
        if not port:
            port = get_port()

        # Start celeryd and redis?
        if hasattr(conf, 'with_async') and conf.with_async:
            from pymacaron_async import start_celery
            start_celery(port, debug)

        # Proceed to start the API server
        callback(port, debug)

    if name == "__main__":
        main()

    if os.path.basename(sys.argv[0]) == 'gunicorn':
        show_splash()
        port = get_port()
        callback(port)

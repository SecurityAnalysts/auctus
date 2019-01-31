import logging
import jinja2
import json
import os
import pkg_resources
import tornado.ioloop
from tornado.routing import URLSpec
import tornado.web
from tornado.web import HTTPError, RequestHandler

logger = logging.getLogger(__name__)


class BaseHandler(RequestHandler):
    """Base class for all request handlers.
    """
    template_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            [pkg_resources.resource_filename('web_discovery',
                                             'templates')]
        ),
        autoescape=jinja2.select_autoescape(['html'])
    )

    @jinja2.contextfunction
    def _tpl_static_url(context, path):
        v = not context['handler'].application.settings.get('debug', False)
        return context['handler'].static_url(path, include_version=v)
    template_env.globals['static_url'] = _tpl_static_url

    @jinja2.contextfunction
    def _tpl_reverse_url(context, path, *args):
        return context['handler'].reverse_url(path, *args)
    template_env.globals['reverse_url'] = _tpl_reverse_url

    @jinja2.contextfunction
    def _tpl_xsrf_form_html(context):
        return jinja2.Markup(context['handler'].xsrf_form_html())
    template_env.globals['xsrf_form_html'] = _tpl_xsrf_form_html

    template_env.globals['islist'] = lambda v: isinstance(v, (list, tuple))
    template_env.globals['isdict'] = lambda v: isinstance(v, dict)

    def render_string(self, template_name, **kwargs):
        template = self.template_env.get_template(template_name)
        return template.render(
            handler=self,
            current_user=self.current_user,
            query_host=os.environ.get('QUERY_HOST', ''),
            **kwargs)

    def get_json(self):
        type_ = self.request.headers.get('Content-Type', '')
        if not type_.startswith('application/json'):
            raise HTTPError(400, "Expected JSON")
        return json.loads(self.request.body.decode('utf-8'))

    def send_json(self, obj):
        if isinstance(obj, list):
            obj = {'results': obj}
        elif not isinstance(obj, dict):
            raise ValueError("Can't encode %r to JSON" % type(obj))
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        return self.finish(json.dumps(obj))


class Index(BaseHandler):
    def get(self):
        self.render('index.html')


class Pages(BaseHandler):
    def post(self):
        obj = self.get_json()
        query = obj['keywords']
        # TODO: Bing search
        return self.send_json({
            'pages': [
                {
                    'title': "Result 1",
                    'url': 'http://url.of.result.1/page/from/bing',
                    'files': [
                        {
                            'url': 'http://url.of.result.1/file1.csv',
                            'format': 'CSV',
                        },
                        {
                            'url': 'http://url.of.result.1/extra/another.file.csv',
                            'format': 'XSLX',
                        },
                        {
                            'url': 'http://url.of.result.1/already.processed.file.csv',
                            'format': 'CSV',
                            'status': 'indexed',
                        },
                    ],
                },
                {
                    'title': "Result 2",
                    'url': 'http://another.result/with.a/different/url.html',
                    'files': [
                        {
                            'url': 'http://url.of.result.1/file1.csv',
                            'format': 'CSV',
                        },
                    ],
                },
            ],
        })


class Profile(BaseHandler):
    def post(self):
        obj = self.get_json()
        # TODO: "discover" those datasets (send for profiling)


def make_web_discovery_app(debug=False):
    if 'XDG_CACHE_HOME' in os.environ:
        cache = os.environ['XDG_CACHE_HOME']
    else:
        cache = os.path.expanduser('~/.cache')
    os.makedirs(cache, 0o700, exist_ok=True)
    cache = os.path.join(cache, 'datamart.json')
    secret = None
    try:
        fp = open(cache)
    except IOError:
        pass
    else:
        try:
            secret = json.load(fp)['cookie_secret']
            fp.close()
        except Exception:
            logger.exception("Couldn't load cookie secret from cache file")
        if not isinstance(secret, str) or not 10 <= len(secret) < 2048:
            logger.error("Invalid cookie secret in cache file")
            secret = None
    if secret is None:
        secret = os.urandom(30).decode('iso-8859-15')
        try:
            fp = open(cache, 'w')
            json.dump({'cookie_secret': secret}, fp)
            fp.close()
        except IOError:
            logger.error("Couldn't open cache file, cookie secret won't be "
                         "persisted! Users will be logged out if you restart "
                         "the program.")

    return tornado.web.Application(
        [
            URLSpec('/', Index, name='index'),
            URLSpec('/pages', Pages, name='pages'),
        ],
        static_path=pkg_resources.resource_filename('web_discovery',
                                                    'static'),
        debug=debug,
        serve_traceback=True,
        cookie_secret=secret,
    )

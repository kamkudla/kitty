#!/usr/bin/env python
# vim:fileencoding=utf-8
#
# Configuration file for the Sphinx documentation builder.
#
# This file does only contain a selection of the most common options. For a
# full list see the documentation:
# https://www.sphinx-doc.org/en/master/config

import glob
import os
import re
import subprocess
import sys
import time
from functools import lru_cache, partial
from typing import Any, Callable, Dict, Iterable, List, Tuple

from docutils import nodes
from docutils.parsers.rst.roles import set_classes
from pygments.lexer import RegexLexer, bygroups  # type: ignore
from pygments.token import Comment, Keyword, Literal, Name, Number, String, Whitespace  # type: ignore
from sphinx import addnodes, version_info
from sphinx.util.logging import getLogger

kitty_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if kitty_src not in sys.path:
    sys.path.insert(0, kitty_src)

from kitty.conf.types import Definition, expand_opt_references  # noqa
from kitty.constants import str_version, website_url # noqa

# config {{{
# -- Project information -----------------------------------------------------

project = 'kitty'
copyright = time.strftime('%Y, Kovid Goyal')
author = 'Kovid Goyal'
building_man_pages = 'man' in sys.argv

# The short X.Y version
version = str_version
# The full version, including alpha/beta/rc tags
release = str_version
logger = getLogger(__name__)


# -- General configuration ---------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
needs_sphinx = '1.7'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.ifconfig',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
    'sphinx.ext.extlinks',
    'sphinx_copybutton',
    'sphinx_inline_tabs',
    "sphinxext.opengraph",
]

# URL for OpenGraph tags
ogp_site_url = website_url()
# OGP needs a PNG image because of: https://github.com/wpilibsuite/sphinxext-opengraph/issues/96
ogp_social_cards = {
    'image': '../logo/kitty.png'
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language: str = 'en'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path .
exclude_patterns = [
    '_build', 'Thumbs.db', '.DS_Store', 'basic.rst',
    'generated/cli-*.rst', 'generated/conf-*.rst', 'generated/actions.rst'
]

rst_prolog = '''
.. |kitty| replace:: *kitty*
.. |version| replace:: VERSION
.. _tarball: https://github.com/kovidgoyal/kitty/releases/download/vVERSION/kitty-VERSION.tar.xz
.. role:: italic

'''.replace('VERSION', str_version)
smartquotes_action = 'qe'  # educate quotes and ellipses but not dashes

def go_version(go_mod_path: str) -> str:  # {{{
    with open(go_mod_path) as f:
        for line in f:
            if line.startswith('go '):
                return line.strip().split()[1]
    raise SystemExit(f'No Go version in {go_mod_path}')
# }}}

string_replacements = {
    '_kitty_install_cmd': 'curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin',
    '_build_go_version': go_version('../go.mod'),
}


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'furo'
html_title = 'kitty'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
github_icon_path = 'M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z'  # noqa

html_theme_options: Dict[str, Any] = {
    'sidebar_hide_name': True,
    'navigation_with_keys': True,
    'footer_icons': [
        {
            "name": "GitHub",
            "url": "https://github.com/kovidgoyal/kitty",
            "html": f"""
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="{github_icon_path}"></path>
                </svg>
            """,
            "class": "",
        },
    ],
}


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_favicon = html_logo = '../logo/kitty.svg'
html_css_files = ['custom.css', 'timestamps.css']
html_js_files = ['custom.js', 'timestamps.js']

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# The default sidebars (for documents that don't match any pattern) are
# defined by theme itself.  Builtin themes are using these templates by
# default: ``['localtoc.html', 'relations.html', 'sourcelink.html',
# 'searchbox.html']``.
#
html_show_sourcelink = False
html_show_sphinx = False
manpages_url = 'https://man7.org/linux/man-pages/man{section}/{page}.{section}.html'

# -- Options for manual page output ------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('invocation', 'kitty', 'The fast, feature rich terminal emulator', [author], 1),
    ('conf', 'kitty.conf', 'Configuration file for kitty', [author], 5)
]


# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'kitty', 'kitty Documentation',
     author, 'kitty', 'Cross-platform, fast, feature-rich, GPU based terminal',
     'Miscellaneous'),
]
# }}}


# GitHub linking inline roles {{{

extlinks = {
    'iss': ('https://github.com/kovidgoyal/kitty/issues/%s', '#%s'),
    'pull': ('https://github.com/kovidgoyal/kitty/pull/%s', '#%s'),
    'disc': ('https://github.com/kovidgoyal/kitty/discussions/%s', '#%s'),
}


def commit_role(
    name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Any = {}, content: Any = []
) -> Tuple[List[nodes.reference], List[nodes.problematic]]:
    ' Link to a github commit '
    try:
        commit_id = subprocess.check_output(
            f'git rev-list --max-count=1 --skip=# {text}'.split()).decode('utf-8').strip()
    except Exception:
        msg = inliner.reporter.error(
            f'GitHub commit id "{text}" not recognized.', line=lineno)
        prb = inliner.problematic(rawtext, rawtext, msg)
        return [prb], [msg]
    url = f'https://github.com/kovidgoyal/kitty/commit/{commit_id}'
    set_classes(options)
    short_id = subprocess.check_output(
        f'git rev-list --max-count=1 --abbrev-commit --skip=# {commit_id}'.split()).decode('utf-8').strip()
    node = nodes.reference(rawtext, f'commit: {short_id}', refuri=url, **options)
    return [node], []
# }}}


# CLI docs {{{
def write_cli_docs(all_kitten_names: Iterable[str]) -> None:
    from kittens.ssh.main import copy_message, option_text
    from kitty.cli import option_spec_as_rst
    with open('generated/ssh-copy.rst', 'w') as f:
        f.write(option_spec_as_rst(
            appname='copy', ospec=option_text, heading_char='^',
            usage='file-or-dir-to-copy ...', message=copy_message
        ))
    del sys.modules['kittens.ssh.main']

    from kitty.launch import options_spec as launch_options_spec
    with open('generated/launch.rst', 'w') as f:
        f.write(option_spec_as_rst(
            appname='launch', ospec=launch_options_spec, heading_char='_',
            message='''\
Launch an arbitrary program in a new kitty window/tab. Note that
if you specify a program-to-run you can use the special placeholder
:code:`@selection` which will be replaced by the current selection.
'''
        ))
    with open('generated/cli-kitty.rst', 'w') as f:
        f.write(option_spec_as_rst(appname='kitty').replace(
            'kitty --to', 'kitty @ --to'))
    as_rst = partial(option_spec_as_rst, heading_char='_')
    from kitty.rc.base import all_command_names, command_for_name
    from kitty.remote_control import cli_msg, global_options_spec
    with open('generated/cli-kitten-at.rst', 'w') as f:
        p = partial(print, file=f)
        p('kitten @')
        p('-' * 80)
        p('.. program::', 'kitten @')
        p('\n\n' + as_rst(
            global_options_spec, message=cli_msg, usage='command ...', appname='kitten @'))
        from kitty.rc.base import cli_params_for
        for cmd_name in sorted(all_command_names()):
            func = command_for_name(cmd_name)
            p(f'.. _at-{func.name}:\n')
            p('kitten @', func.name)
            p('-' * 120)
            p('.. program::', 'kitten @', func.name)
            p('\n\n' + as_rst(*cli_params_for(func)))
    from kittens.runner import get_kitten_cli_docs

    for kitten in all_kitten_names:
        data = get_kitten_cli_docs(kitten)
        if data:
            with open(f'generated/cli-kitten-{kitten}.rst', 'w') as f:
                p = partial(print, file=f)
                p('.. program::', 'kitty +kitten', kitten)
                p('\nSource code for', kitten)
                p('-' * 72)
                scurl = f'https://github.com/kovidgoyal/kitty/tree/master/kittens/{kitten}'
                p(f'\nThe source code for this kitten is `available on GitHub <{scurl}>`_.')
                p('\nCommand Line Interface')
                p('-' * 72)
                p('\n\n' + option_spec_as_rst(
                    data['options'], message=data['help_text'], usage=data['usage'], appname=f'kitty +kitten {kitten}',
                    heading_char='^'))

# }}}


def write_remote_control_protocol_docs() -> None:  # {{{
    from kitty.rc.base import RemoteCommand, all_command_names, command_for_name
    field_pat = re.compile(r'\s*([^:]+?)\s*:\s*(.+)')

    def format_cmd(p: Callable[..., None], name: str, cmd: RemoteCommand) -> None:
        p(name)
        p('-' * 80)
        lines = (cmd.__doc__ or '').strip().splitlines()
        fields = []
        for line in lines:
            m = field_pat.match(line)
            if m is None:
                p(line)
            else:
                fields.append((m.group(1).split('/')[0], m.group(2)))
        if fields:
            p('\nFields are:\n')
            for (name, desc) in fields:
                if '+' in name:
                    title = name.replace('+', ' (required)')
                else:
                    title = name
                    defval = cmd.get_default(name.replace('-', '_'), cmd)
                    if defval is not cmd:
                        title = f'{title} (default: {defval})'
                    else:
                        title = f'{title} (optional)'
                p(f':code:`{title}`')
                p(' ', desc), p()
        p(), p()

    with open('generated/rc.rst', 'w') as f:
        p = partial(print, file=f)
        for name in sorted(all_command_names()):
            cmd = command_for_name(name)
            if not cmd.__doc__:
                continue
            name = name.replace('_', '-')
            format_cmd(p, name, cmd)
# }}}


def replace_string(app: Any, docname: str, source: List[str]) -> None:  # {{{
    src = source[0]
    for k, v in app.config.string_replacements.items():
        src = src.replace(k, v)
    source[0] = src
# }}}

# config file docs {{{


class ConfLexer(RegexLexer):  # type: ignore
    name = 'Conf'
    aliases = ['conf']
    filenames = ['*.conf']

    tokens = {
        'root': [
            (r'#.*?$', Comment.Single),
            (r'\s+$', Whitespace),
            (r'\s+', Whitespace),
            (r'(include)(\s+)(.+?)$', bygroups(Comment.Preproc, Whitespace, Name.Namespace)),
            (r'(map)(\s+)(\S+)(\s+)', bygroups(
                Keyword.Declaration, Whitespace, String, Whitespace), 'action'),
            (r'(mouse_map)(\s+)(\S+)(\s+)(\S+)(\s+)(\S+)(\s+)', bygroups(
                Keyword.Declaration, Whitespace, String, Whitespace, Name.Variable, Whitespace, String, Whitespace), 'action'),
            (r'(symbol_map)(\s+)(\S+)(\s+)(.+?)$', bygroups(
                Keyword.Declaration, Whitespace, String, Whitespace, Literal)),
            (r'([a-zA-Z_0-9]+)(\s+)', bygroups(
                Name.Variable, Whitespace), 'args'),
        ],
        'action': [
            (r'[a-z_0-9]+$', Name.Function, 'root'),
            (r'[a-z_0-9]+', Name.Function, 'args'),
        ],
        'args': [
            (r'\s+', Whitespace, 'args'),
            (r'\b(yes|no)\b$', Number.Bin, 'root'),
            (r'\b(yes|no)\b', Number.Bin, 'args'),
            (r'[+-]?[0-9]+\s*$', Number.Integer, 'root'),
            (r'[+-]?[0-9.]+\s*$', Number.Float, 'root'),
            (r'[+-]?[0-9]+', Number.Integer, 'args'),
            (r'[+-]?[0-9.]+', Number.Float, 'args'),
            (r'#[a-fA-F0-9]{3,6}\s*$', String, 'root'),
            (r'#[a-fA-F0-9]{3,6}\s*', String, 'args'),
            (r'.+', String, 'root'),
        ],
    }


class SessionLexer(RegexLexer):  # type: ignore
    name = 'Session'
    aliases = ['session']
    filenames = ['*.session']

    tokens = {
        'root': [
            (r'#.*?$', Comment.Single),
            (r'[a-z][a-z0-9_]+', Name.Function, 'args'),
        ],
        'args': [
            (r'.*?$', Literal, 'root'),
        ]
    }


def link_role(
    name: str, rawtext: str, text: str, lineno: int, inliner: Any, options: Any = {}, content: Any = []
) -> Tuple[List[nodes.reference], List[nodes.problematic]]:
    text = text.replace('\n', ' ')
    m = re.match(r'(.+)\s+<(.+?)>', text)
    if m is None:
        msg = inliner.reporter.error(f'link "{text}" not recognized', line=lineno)
        prb = inliner.problematic(rawtext, rawtext, msg)
        return [prb], [msg]
    text, url = m.group(1, 2)
    url = url.replace(' ', '')
    set_classes(options)
    node = nodes.reference(rawtext, text, refuri=url, **options)
    return [node], []


opt_aliases: Dict[str, str] = {}
shortcut_slugs: Dict[str, Tuple[str, str]] = {}


def parse_opt_node(env: Any, sig: str, signode: Any) -> str:
    """Transform an option description into RST nodes."""
    count = 0
    firstname = ''
    for potential_option in sig.split(', '):
        optname = potential_option.strip()
        if count:
            signode += addnodes.desc_addname(', ', ', ')
        text = optname.split('.', 1)[-1]
        signode += addnodes.desc_name(text, text)
        if not count:
            firstname = optname
            signode['allnames'] = [optname]
        else:
            signode['allnames'].append(optname)
            opt_aliases[optname] = firstname
        count += 1
    if not firstname:
        raise ValueError(f'{sig} is not a valid opt')
    return firstname


def parse_shortcut_node(env: Any, sig: str, signode: Any) -> str:
    """Transform a shortcut description into RST nodes."""
    conf_name, text = sig.split('.', 1)
    signode += addnodes.desc_name(text, text)
    return sig


def parse_action_node(env: Any, sig: str, signode: Any) -> str:
    """Transform an action description into RST nodes."""
    signode += addnodes.desc_name(sig, sig)
    return sig


def process_opt_link(env: Any, refnode: Any, has_explicit_title: bool, title: str, target: str) -> Tuple[str, str]:
    conf_name, opt = target.partition('.')[::2]
    if not opt:
        conf_name, opt = 'kitty', conf_name
    full_name = f'{conf_name}.{opt}'
    return title, opt_aliases.get(full_name, full_name)


def process_action_link(env: Any, refnode: Any, has_explicit_title: bool, title: str, target: str) -> Tuple[str, str]:
    return title, target


def process_shortcut_link(env: Any, refnode: Any, has_explicit_title: bool, title: str, target: str) -> Tuple[str, str]:
    conf_name, slug = target.partition('.')[::2]
    if not slug:
        conf_name, slug = 'kitty', conf_name
    full_name = f'{conf_name}.{slug}'
    try:
        target, stitle = shortcut_slugs[full_name]
    except KeyError:
        logger.warning(f'Unknown shortcut: {target}', location=refnode)
    else:
        if not has_explicit_title:
            title = stitle
    return title, target


def write_conf_docs(app: Any, all_kitten_names: Iterable[str]) -> None:
    app.add_lexer('conf', ConfLexer() if version_info[0] < 3 else ConfLexer)
    app.add_object_type(
        'opt', 'opt',
        indextemplate="pair: %s; Config Setting",
        parse_node=parse_opt_node,
    )
    # Warn about opt references that could not be resolved
    opt_role = app.registry.domain_roles['std']['opt']
    opt_role.warn_dangling = True
    opt_role.process_link = process_opt_link

    app.add_object_type(
        'shortcut', 'sc',
        indextemplate="pair: %s; Keyboard Shortcut",
        parse_node=parse_shortcut_node,
    )
    sc_role = app.registry.domain_roles['std']['sc']
    sc_role.warn_dangling = True
    sc_role.process_link = process_shortcut_link
    shortcut_slugs.clear()

    app.add_object_type(
        'action', 'ac',
        indextemplate="pair: %s; Action",
        parse_node=parse_action_node,
    )
    ac_role = app.registry.domain_roles['std']['ac']
    ac_role.warn_dangling = True
    ac_role.process_link = process_action_link

    def generate_default_config(definition: Definition, name: str) -> None:
        with open(f'generated/conf-{name}.rst', 'w', encoding='utf-8') as f:
            print('.. highlight:: conf\n', file=f)
            f.write('\n'.join(definition.as_rst(name, shortcut_slugs)))

        conf_name = re.sub(r'^kitten-', '', name) + '.conf'
        with open(f'generated/conf/{conf_name}', 'w', encoding='utf-8') as f:
            text = '\n'.join(definition.as_conf(commented=True))
            print(text, file=f)

    from kitty.options.definition import definition
    generate_default_config(definition, 'kitty')

    from kittens.runner import get_kitten_conf_docs
    for kitten in all_kitten_names:
        defn = get_kitten_conf_docs(kitten)
        if defn is not None:
            generate_default_config(defn, f'kitten-{kitten}')

    from kitty.actions import as_rst
    with open('generated/actions.rst', 'w', encoding='utf-8') as f:
        f.write(as_rst())
# }}}


def add_html_context(app: Any, pagename: str, templatename: str, context: Any, doctree: Any, *args: Any) -> None:
    context['analytics_id'] = app.config.analytics_id
    if 'toctree' in context:
        # this is needed with furo to use all titles from pages
        # in the sidebar (global) toc
        original_toctee_function = context['toctree']

        def include_sub_headings(**kwargs: Any) -> Any:
            kwargs['titles_only'] = False
            return original_toctee_function(**kwargs)

        context['toctree'] = include_sub_headings


@lru_cache
def monkeypatch_man_writer() -> None:
    '''
    Monkeypatch the docutils man translator to be nicer
    '''
    from docutils.nodes import Element
    from docutils.writers.manpage import Table, Translator
    from sphinx.writers.manpage import ManualPageTranslator

    # Generate nicer tables https://sourceforge.net/p/docutils/bugs/475/
    class PatchedTable(Table):  # type: ignore
        _options: list[str]
        def __init__(self) -> None:
            super().__init__()
            self.needs_border_removal = self._options == ['center']
            if self.needs_border_removal:
                self._options = ['box', 'center']

        def as_list(self) -> list[str]:
            ans: list[str] = super().as_list()
            if self.needs_border_removal:
                # remove side and top borders as we use box in self._options
                ans[2] = ans[2][1:]
                a, b = ans[2].rpartition('|')[::2]
                ans[2] = a + b
                if ans[3] == '_\n':
                    del ans[3]  # top border
                del ans[-2] # bottom border
            return ans
    def visit_table(self: ManualPageTranslator, node: object) -> None:
        setattr(self, '_active_table', PatchedTable())
    setattr(ManualPageTranslator, 'visit_table', visit_table)

    # Improve header generation
    def header(self: ManualPageTranslator) -> str:
        di = getattr(self, '_docinfo')
        di['ktitle'] = di['title'].replace('_', '-')
        th = (".TH \"%(ktitle)s\" %(manual_section)s"
              " \"%(date)s\" \"%(version)s\"") % di
        if di["manual_group"]:
            th += " \"%(manual_group)s\"" % di
        th += "\n"
        sh_tmpl: str = (".SH Name\n"
                   "%(ktitle)s \\- %(subtitle)s\n")
        return th + sh_tmpl % di  # type: ignore

    setattr(ManualPageTranslator, 'header', header)

    def visit_image(self: ManualPageTranslator, node: Element) -> None:
        pass

    def depart_image(self: ManualPageTranslator, node: Element) -> None:
        pass

    def depart_figure(self: ManualPageTranslator, node: Element) -> None:
        self.body.append(' (images not supported)\n')
        Translator.depart_figure(self, node)

    setattr(ManualPageTranslator, 'visit_image', visit_image)
    setattr(ManualPageTranslator, 'depart_image', depart_image)
    setattr(ManualPageTranslator, 'depart_figure', depart_figure)

    orig_astext = Translator.astext
    def astext(self: Translator) -> Any:
        b = []
        for line in self.body:
            if line.startswith('.SH'):
                x, y = line.split(' ', 1)
                parts = y.splitlines(keepends=True)
                parts[0] = parts[0].capitalize()
                line = x + ' ' + '\n'.join(parts)
            b.append(line)
        self.body = b
        return orig_astext(self)
    setattr(Translator, 'astext', astext)


def setup_man_pages() -> None:
    from kittens.runner import get_kitten_cli_docs
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for x in glob.glob(os.path.join(base, 'docs/kittens/*.rst')):
        kn = os.path.basename(x).rpartition('.')[0]
        if kn == 'custom':
            continue
        cd = get_kitten_cli_docs(kn) or {}
        khn = kn.replace('_', '-')
        man_pages.append((f'kittens/{kn}', 'kitten-' + khn, cd.get('short_desc', 'kitten Documentation'), [author], 1))
    monkeypatch_man_writer()


def build_extra_man_pages() -> None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kitten = os.environ.get('KITTEN_EXE_FOR_DOCS', os.path.join(base, 'kitty/launcher/kitten'))
    if not os.path.exists(kitten):
        subprocess.call(['find', os.path.dirname(kitten)])
        raise Exception(f'The kitten binary {kitten} is not built cannot generate man pages')
    raw = subprocess.check_output([kitten, '-h']).decode()
    started = 0
    names = set()
    for line in raw.splitlines():
        if line.strip() == '@':
            started = len(line.rstrip()[:-1])
        q = line.strip()
        if started and len(q.split()) == 1 and not q.startswith('-') and ':' not in q:
            if len(line) - len(line.lstrip()) == started:
                if not os.path.exists(os.path.join(base, f'docs/kittens/{q}.rst')):
                    names.add(q)
    cwd = os.path.join(base, 'docs/_build/man')
    subprocess.check_call([kitten, '__generate_man_pages__'], cwd=cwd)
    subprocess.check_call([kitten, '__generate_man_pages__'] + list(names), cwd=cwd)


if building_man_pages:
    setup_man_pages()


def build_finished(*a: Any, **kw: Any) -> None:
    if building_man_pages:
        build_extra_man_pages()


def setup(app: Any) -> None:
    os.makedirs('generated/conf', exist_ok=True)
    from kittens.runner import all_kitten_names
    kn = all_kitten_names()
    write_cli_docs(kn)
    write_remote_control_protocol_docs()
    write_conf_docs(app, kn)
    app.add_config_value('string_replacements', {}, True)
    app.connect('source-read', replace_string)
    app.add_config_value('analytics_id', '', 'env')
    app.connect('html-page-context', add_html_context)
    app.connect('build-finished', build_finished)
    app.add_lexer('session', SessionLexer() if version_info[0] < 3 else SessionLexer)
    app.add_role('link', link_role)
    app.add_role('commit', commit_role)

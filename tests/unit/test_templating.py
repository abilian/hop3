# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: MIT

# ruff: noqa: W293

from hop3.util.templating import eval_template

TEMPLATE = """\
<html>
  <body>
  {% for-in(post, posts) %}
  <article>
    <h1>{{ get(post, 'title') }}</h1>
    <p>
      {{ get(post, 'body') }}
    </p>
  </article>
  {% endfor-in %}
  </body>
</html>
"""

ENV = {
    "posts": [
        {
            "title": "Hello world!",
            "body": "This is my first post!",
        },
        {
            "title": "Take two",
            "body": "This is a second post.",
        },
    ],
}

EXPECTED = """\
<html>
  <body>

  <article>
    <h1>Hello world!</h1>
    <p>
      This is my first post!
    </p>
  </article>

  <article>
    <h1>Take two</h1>
    <p>
      This is a second post.
    </p>
  </article>

  </body>
</html>
"""


def test_eval_template():
    result = eval_template(TEMPLATE, ENV)
    for line1, line2 in zip(result.split("\n"), EXPECTED.split("\n")):
        assert line1.rstrip() == line2.rstrip()

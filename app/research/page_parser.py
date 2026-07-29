from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html
from trafilatura import extract
from trafilatura.metadata import extract_metadata

from app.research.contracts import ExtractedSection, ParsedPage


def _clean_text(element) -> str:
    return " ".join(element.text_content().split())


def _absolute_permalink(base_url: str, value: str | None) -> str:
    return urljoin(base_url, value or base_url)


def _remove_hidden_content(html: str) -> str:
    tree = lxml_html.fromstring(html)
    hidden_nodes = tree.xpath(
        "//script | //style | //noscript | //template | //*[@hidden] | "
        '//*[@aria-hidden="true"] | '
        '//*[contains(translate(@style, "ABCDEFGHIJKLMNOPQRSTUVWXYZ ", '
        '"abcdefghijklmnopqrstuvwxyz"), "display:none")] | '
        '//*[contains(translate(@style, "ABCDEFGHIJKLMNOPQRSTUVWXYZ ", '
        '"abcdefghijklmnopqrstuvwxyz"), "visibility:hidden")]'
    )
    for node in hidden_nodes:
        node.drop_tree()
    return lxml_html.tostring(tree, encoding="unicode")


def _parse_reddit_sections(html: str, url: str) -> tuple[str, list[ExtractedSection]]:
    tree = lxml_html.fromstring(html)
    posts = tree.xpath("//shreddit-post")
    post_parts = posts[0].xpath('.//*[@slot="text-body"]') if posts else []
    post_text = _clean_text(post_parts[0]) if post_parts else ""

    sections: list[ExtractedSection] = []
    root_comments = tree.xpath('//shreddit-comment[@depth="0"]')[:10]
    for root in root_comments:
        root_permalink = _absolute_permalink(url, root.get("permalink"))
        bodies = root.xpath('./*[@slot="comment"]')
        if bodies and (text := _clean_text(bodies[0])):
            sections.append(
                ExtractedSection(
                    kind="comment",
                    text=text,
                    permalink=root_permalink,
                )
            )
        for reply in root.xpath('.//shreddit-comment[@depth="1"]'):
            reply_bodies = reply.xpath('./*[@slot="comment"]')
            if reply_bodies and (text := _clean_text(reply_bodies[0])):
                sections.append(
                    ExtractedSection(
                        kind="reply",
                        text=text,
                        permalink=_absolute_permalink(url, reply.get("permalink")),
                        parent_permalink=root_permalink,
                    )
                )
    return post_text, sections


def parse_html_page(html: str, url: str) -> ParsedPage:
    html = _remove_hidden_content(html)
    metadata = extract_metadata(html, default_url=url)
    text = extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    sections: list[ExtractedSection] = []
    if urlsplit(url).hostname in {"reddit.com", "www.reddit.com", "old.reddit.com"}:
        reddit_text, sections = _parse_reddit_sections(html, url)
        text = reddit_text or text

    canonical_url = metadata.url or url
    title = metadata.title or ""
    return ParsedPage(
        canonical_url=canonical_url,
        title=title,
        publisher=metadata.sitename,
        published_at=metadata.date,
        text=(text or "").strip(),
        sections=sections,
    )

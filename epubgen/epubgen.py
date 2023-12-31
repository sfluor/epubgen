import os
from zipfile import ZipFile
from datetime import datetime
import xml.etree.ElementTree as ET
import io

CONTENT_ROOT = "EPUB/"
TOC_PATH = "toc.xhtml"
PACKAGE_PATH = CONTENT_ROOT + "package.opf"
TOC_ID = "toc"
TOC_NAME = "Table of contents"
CSS_FILE = "stylesheet.css"


def xml_to_str(xml: ET.Element) -> str:
    return ET.tostring(xml, encoding="unicode", method="xml", xml_declaration=True)


class EPUB:
    """
    A class used to represent an EPUB being built

    Parameters
    ----------
    - title: the title of the EPUB
    - author: the author of the EPUB
    - language: the main language of the generated EPUB
    - id: a public identifier for the EPUB
    - css: optional CSS to provide to tweak the presentation of the pages
    - rtl: to enable the "right to left" reading direction mode

    Methods
    -------
    - add_page: add content to the EPUB
    - add_font: add a font to the EPUB
    - add_image: embed images in the EPUB
    - add_cover: add a cover image for the EPUB
    - to_disk: generate the EPUB file and writes it to disk
    - to_bytes: generate the EPUB file and returns a BytesIO buffer
    """

    def __init__(
        self, title: str, author: str, language: str, id: str, css="", rtl=False
    ):
        self.id: str = id
        self.rtl: bool = rtl
        self.metadata: ET.Element = self._generate_pkg_metadata(title, author, language)
        self.manifest: ET.Element = ET.Element("manifest")
        spine_attrs = {}
        if self.rtl:
            spine_attrs["page-progression-direction"] = "rtl"
        self.spine: ET.Element = ET.Element("spine", attrib=spine_attrs)
        self.toc = ET.Element("ol")
        self.css = css

        # Add the table of contents to the spine and the manifest
        self._add_to_manifest_and_spine(TOC_ID, TOC_PATH, properties="nav")

        self.page_counts: int = 0
        self.contents: list[tuple[str, str | bytes]] = [
            ("mimetype", "application/epub+zip"),
            ("META-INF/container.xml", self._generate_container()),
        ]

    def _generate_container(self) -> str:
        container = ET.Element(
            "container",
            attrib={
                "xmlns": "urn:oasis:names:tc:opendocument:xmlns:container",
                "version": "1.0",
            },
        )
        rootfiles = ET.SubElement(container, "rootfiles")
        ET.SubElement(
            rootfiles,
            "rootfile",
            attrib={
                "full-path": PACKAGE_PATH,
                "media-type": "application/oebps-package+xml",
            },
        )
        return xml_to_str(container)

    def _add_to_manifest(self, id, path, media_type, **kwargs):
        ET.SubElement(
            self.manifest,
            "item",
            attrib={
                "id": id,
                "href": path,
                "media-type": media_type,
                **kwargs,
            },
        )

    def _current_page_id_and_path(self) -> tuple[str, str]:
        page_id = f"page{self.page_counts}"
        path = f"{page_id}.xhtml"
        return (page_id, path)

    def _add_to_manifest_and_spine(self, page_id: str, path: str, **kwargs):
        self._add_to_manifest(page_id, path, "application/xhtml+xml", **kwargs)
        ET.SubElement(self.spine, "itemref", idref=page_id)

    # Returns the path of the table of contents
    def _generate_toc(self) -> str:
        html = ET.Element(
            "html",
            attrib={
                "xmlns": "http://www.w3.org/1999/xhtml",
                "xmlns:epub": "http://www.idpf.org/2007/ops",
            },
        )
        head = ET.SubElement(html, "head")
        title = ET.SubElement(head, "title")
        title.text = TOC_NAME

        body = ET.SubElement(html, "body")
        h1 = ET.SubElement(body, "h1")
        h1.text = TOC_NAME

        nav = ET.SubElement(
            body, "nav", attrib={"epub:type": "toc", "id": TOC_ID, "role": "doc-toc"}
        )

        nav.append(self.toc)

        return xml_to_str(html)

    def _generate_pkg_opf(self) -> str:
        pkg = ET.Element(
            "package",
            attrib={
                "xmlns": "http://www.idpf.org/2007/opf",
                "version": "3.0",
                "xmlns:dc": "http://purl.org/dc/elements/1.1/",
                "xmlns:dcterms": "http://purl.org/dc/terms/",
                "unique-identifier": "pub-identifier",
            },
        )
        pkg.append(self.metadata)
        pkg.append(self.manifest)
        pkg.append(self.spine)

        return xml_to_str(pkg)

    def _generate_pkg_metadata(
        self, title: str, author: str, language: str
    ) -> ET.Element:
        metadata = ET.Element("metadata")

        identifier_t = ET.SubElement(metadata, "dc:identifier", id="pub-identifier")
        identifier_t.text = self.id

        title_t = ET.SubElement(metadata, "dc:title")
        title_t.text = title

        author_t = ET.SubElement(metadata, "dc:creator")
        author_t.text = author

        lang_t = ET.SubElement(metadata, "dc:language")
        lang_t.text = language

        now = datetime.now().strftime("%Y-%m-%dT%H:%m:%SZ")

        date_t = ET.SubElement(metadata, "dc:date")
        date_t.text = now

        meta_t = ET.SubElement(metadata, "meta", property="dcterms:modified")
        meta_t.text = now

        return metadata

    def add_cover(self, image_type:str, cover_content: bytes):
        """
        Add a cover image for the EPUB

        - image_type: the encoding of the image (jpg, png, ...)
        - cover_content: the raw image content as bytes
        """

        COVER = "cover"
        path = f"{COVER}.{image_type}"
        ET.SubElement(self.metadata, "meta", name=COVER, content=COVER)
        self._add_to_manifest(COVER, path, f"image/{image_type}")
        self.contents.append((CONTENT_ROOT + path, cover_content))

    def add_image(self, id: str, path: str, image_content: bytes):
        """
        Embeds an image to the epub that can then be referenced using the provided path.

        - id: the image ID as a string
        - path: the image path in the EPUB as a string (should contain a valid image extension)
        - image_content: the raw image content as bytes
        """
        media_type = os.path.splitext(path)[1][1:]
        self._add_to_manifest(id, path, f"image/{media_type}")
        self.contents.append((CONTENT_ROOT + path, image_content))

    def add_font(self, family: str, style: str, weight: int, font_type: str, font_definition: bytes):
        """
        Embeds a font definition into the epub that can then be used in CSS.

        - family: the font family, for instance "Times New Roman"
        - style: the font style (normal, bold, italic)
        - weight: the font weight (200, 400, 700, etc)
        - type: font type (ttf, otf, woff, etc)
        - font_definition: the raw font definition data (coming from the font file)
        """
        path = f"fonts/{family}-{style}-{weight}.{font_type}"
        self._add_to_manifest(family, path, f"font/{font_type}")
        self.contents.append((CONTENT_ROOT + path, font_definition))

        # We also need to add the font to the stylesheet so that it's discoverable by the epub reader.
        self.css += f"""
@font-face {{
    font-family : "{family}";
    font-weight : {weight};
    font-style: {style};
    src : url("{path}");
}}"""

    def add_page(self, content: ET.Element, toc_title=None):
        """
        Add a new page to the EPUB.

        - content: the HTML content of the page to add
        - [toc_title]: optional, if provided it will add a reference to this page to the table of contents.
        """
        self.page_counts += 1
        page_id, path = self._current_page_id_and_path()

        page_t = ET.Element(
            "html",
            xmlns="http://www.w3.org/1999/xhtml",
            dir=("rtl" if self.rtl else "ltr"),
        )
        head_t = ET.SubElement(page_t, "head")
        title_t = ET.SubElement(head_t, "title")
        title_t.text = page_id

        ET.SubElement(head_t, "link", rel="stylesheet", type="text/css", href=CSS_FILE)

        body_t = ET.SubElement(page_t, "body")
        body_t.append(content)

        self.contents.append((CONTENT_ROOT + path, xml_to_str(page_t)))
        self._add_to_manifest_and_spine(page_id, path)

        if toc_title is not None:
            li = ET.Element("li")
            link = ET.SubElement(li, "a", href=path)
            link.text = toc_title
            self.toc.append(li)

    def to_bytes(self) -> io.BytesIO:
        contents = self.contents
        if self.css:
            contents.append((CONTENT_ROOT + CSS_FILE, self.css))
            self._add_to_manifest("stylesheet", CSS_FILE, "text/css")

        contents = contents + [
            (CONTENT_ROOT + TOC_PATH, self._generate_toc()),
            (PACKAGE_PATH, self._generate_pkg_opf()),
        ]

        buf = io.BytesIO()
        with ZipFile(buf, "a") as zip:
            for path, content in contents:
                zip.writestr(path, content)

        return buf

    def to_disk(self, path: str):
        """
        Generates the EPUB and saves it at the provided path.
        """
        buf : io.BytesIO = self.to_bytes()

        with open(path, "wb") as file:
            file.write(buf.getvalue())

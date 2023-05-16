"""
Publication parser which uses the CrossRef API
to generate the publication list directly from 
a list of article DOIs

Will additionally detect when an arXiv paper has
been published and will prompt the user to update
the published DOI list. 

reads:
    File:  
        ../content/doi_published.txt
        ../content/arXiv_ids.txt

    Description: list of all DOI of published and preprint articles (will be ordered according to date)

    File: 
        ../content/manual_metadata/[doi].json

    Description: Directory of manually included JSON files for the ocassional reference which does not work
         file format is case sensitve and replaces '/' with '-' 
         (e.g. doi of '1011.1213' -> file of '1011-1213.json')
         Note: script will always attempt to find the local version BEFORE attempting to search online
            This is useful for cases where there is a formatting error in the online metadata
     
overwrites:
    ../source/publications


API calls:
    CrossRef (https://api.crossref.org/swagger-ui/index.html)
    ArXiv (https://arxiv.org/help/api/user-manual)
    ChemRXiv (https://chemrxiv.org/engage/chemrxiv/public-api/documentation)


Paul J. Robinson, Columbia University, July 2022
"""

import requests
import feedparser
import json

import numpy as np
from itertools import groupby
from datetime import date

try:
    from tqdm import tqdm
except ImportError:

    def tqdm(iterable):
        return iterable


"""
USER MODIFIABLE
"""
manual_json_dir = "../content/manual_metadata"
doi_file = "../content/doi_published.txt"
arXiv_file = "../content/arXiv_ids.txt"

output_file = "../source/publications"

"""
IMPORTANT Global Variables: Do not change unless API calls change
"""
cr_api_base = "https://api.crossref.org/works/"
cr_api_app = "/transform/application/vnd.citationstyles.csl+json"

chemRXiv_api_base = "http://chemrxiv.org/engage/chemrxiv/public-api/v1/items/doi/"
arXiv_api_base = "http://export.arxiv.org/api/query?id_list="

"""
Code
"""


def main():
    list_of_DOI = np.genfromtxt(doi_file, dtype=str)
    list_of_preprint = np.genfromtxt(arXiv_file, dtype=str)
    error_doi = []
    error_doi_preprint = []
    published_doi_preprint = []

    preprint_json = []
    print("Querying ArXiv and ChemRXiv for Preprint Metadata:")
    for preprint_i in tqdm(list_of_preprint):
        json_i = None
        try:
            json_i = preprint_api_calls(preprint_i)
            try:
                if json_i["status_published"] is True:
                    published_doi_preprint.append(preprint_i)
            except KeyError:
                # preprint publication status unknown
                pass
        except ImportError:
            error_doi_preprint.append(preprint_i)
            continue
        else:
            preprint_json.append(json_i)

    if len(published_doi_preprint) > 0:
        print("The following preprints were detected as having been published:")
        [print("----", i) for i in published_doi_preprint]
        print("Please update entires in ", doi_file, " with the permanent DOI")

    if len(error_doi_preprint) > 0:
        print("The following preprints were not found:")
        [print("----", i) for i in error_doi_preprint]
        print(
            "Please either correct the entry or add a manual metadata file in ",
            manual_json_dir,
        )

    published_json = []
    print("Querying CrossRef and Preprint Servers for Article Metadata:")
    for doi_i in tqdm(list_of_DOI):
        json_i = None
        try:
            json_i = published_api_calls(doi_i)
        except ImportError:
            error_doi.append(doi_i)
            continue
        else:
            published_json.append(json_i)

    if len(error_doi) > 0:
        print("The following papers were not found:")
        [print("----", i) for i in error_doi]
        print(
            "Please either correct the entry or add a manual metadata file in ",
            manual_json_dir,
        )

    published_json = sorted(published_json, key=sort_date_function, reverse=True)

    article_num = len(published_json) + len(preprint_json)

    with open(output_file, "w") as outfile:
        outfile.write('<div id="main"> \n')
        outfile.write("<h2>Publications</h2> \n")
        outfile.write("<h3>Preprints</h3> \n")
        outfile.write('<ol class="pubs"> \n')
        for preprint_i in preprint_json:
            outfile.write(f'<li value="{article_num}">')
            outfile.write("\n")
            outfile.write(f'<a class="anchor" name="preprint_{article_num}"></a>')
            outfile.write("\n")
            outfile.write(format_article(preprint_i))
            outfile.write("\n")
            outfile.write("</li>")
            outfile.write("\n")
            article_num -= 1
        outfile.write("</ol>")
        outfile.write("\n")

        for year_i, jsons_year_i in groupby(published_json, key=sort_year_function):
            outfile.write(f"<h3>{year_i}</h3>")
            outfile.write("\n")
            outfile.write('<ol class="pubs">')
            outfile.write("\n")
            for json_j in jsons_year_i:
                outfile.write(f'<li value="{article_num}">')
                outfile.write("\n")
                outfile.write(f'<a class="anchor" name="article_{article_num}"></a>')
                outfile.write("\n")
                outfile.write(format_article(json_j).rstrip("\n"))
                outfile.write("\n")
                outfile.write("</li>")
                outfile.write("\n")
                article_num -= 1
            outfile.write("</ol>")
            outfile.write("\n")
        outfile.write("</div> <!-- End main -->")


def sort_year_function(j):
    """
    Provides year for each article. If day of month not given then assumes 1st.
    """
    try:
        return j["published"]["date-parts"][0][0]
    except KeyError:
        try:
            return j["created"]["date-parts"][0][0]
        except KeyError:
            return 0


def sort_date_function(j):
    """
    Provides a UNIX time for each article. If day of month not given then assumes 1st.
    """
    try:
        date_list = j["published"]["date-parts"][0]
        if len(date_list) == 2:
            date_list.append(1)
        if len(date_list) < 2:
            raise KeyError
        return date(*date_list)
    except KeyError:
        try:
            date_list = j["created"]["date-parts"][0]
            if len(date_list) == 2:
                date_list.append(1)
            return date(*date_list)
        except KeyError:
            return 0


def published_api_calls(doi):
    """
    Attempts all API calls
    """
    json_return = None
    try:
        json_return = get_manual_json(doi)
    except ImportError:
        try:
            json_return = get_crossRef(doi)
        except ImportError:
            json_return = preprint_api_calls(doi)
    return json_return


def preprint_api_calls(doi):
    """
    Attempts preprint server API calls
    """
    json_return = None
    if "chemrxiv" in doi.lower():
        try:
            json_return = get_manual_json(doi)
        except ImportError:
            json_return = get_chemRXiv(doi)
        return json_return

    elif "arxiv" in doi.lower():
        try:
            json_return = get_manual_json(doi)
        except ImportError:
            json_return = get_arXiv(doi)
        return json_return

    else:
        json_return = get_manual_json(doi)
        return json_return

    raise ImportError


def get_chemRXiv(doi):
    """
    Uses the chemRXiv API to extract metadata
    param: doi (str)

    returns: json object
    """
    req_url = chemRXiv_api_base + doi

    req_json = requests.get(req_url)

    if req_json.status_code == 404:
        raise ImportError

    json_i = req_json.json()
    json_i["container-title"] = "ChemRxiv"
    json_i["published"] = {
        "date-parts": [json_i["publishedDate"].split("T")[0].split("-")]
    }
    json_i["URL"] = "https://doi.org/" + json_i["doi"]

    return json_i


def get_arXiv(prefix):
    """
    Uses the ArXiv API to extract metadata
    param: arxiv prefix (str)

    return: dictionary with same attributes as other JSON objects
    """
    prefix_full = prefix
    if ":" in prefix:
        prefix = prefix.split(":")[1]
    req_url = arXiv_api_base + prefix
    req_xml = requests.get(req_url)
    if req_xml.status_code == 404:
        raise ImportError

    if "incorrect_id_format_for_" + prefix in req_xml.text:
        raise ImportError

    xml_struct = feedparser.parse(req_xml.text)

    authors = xml_struct.entries[0].authors
    title = xml_struct.entries[0].title
    year = xml_struct.entries[0].published_parsed.tm_year
    month = xml_struct.entries[0].published_parsed.tm_mon
    day = xml_struct.entries[0].published_parsed.tm_mday
    # url = xml_struct.entries[0].link
    url = "http://arxiv.org/abs/" + prefix
    article_id = xml_struct.entries[0].id

    published = False
    try:
        xml_struct.entries[0].arxiv_journal_ref
    except AttributeError:
        pass
    else:
        published = True

    for i, author in enumerate(authors):
        fullName = author["name"]
        first = fullName.split(" ")[:-1]
        for j, name in enumerate(first):
            if len(name) == 1:
                first[j] += "."
        first = " ".join(first)
        authors[i] = {"firstName": first, "lastName": fullName.split(" ")[-1]}

    dict_return = {
        "title": title,
        "published": {"date-parts": [[year, month, day]]},
        "authors": authors,
        "URL": url,
        "container-title": prefix_full,
        "status_published": published,
    }

    return dict_return


def get_crossRef(doi):
    """
    Uses the CrossRef API to extract article metaData
    param: doi (str)

    return: json object
    """
    req_url = cr_api_base + doi + cr_api_app

    req_json = requests.get(req_url)

    if req_json.status_code == 404:
        raise ImportError

    json_i = req_json.json()

    return json_i


def get_manual_json(doi):
    """
    Uses locally stored JSON files
    """
    return_json = None
    fileName = (
        manual_json_dir
        + "/"
        + doi.replace("/", "-").replace(":", "-").strip()
        + ".json"
    )
    try:
        with open(fileName, "r") as json_file:
            return_json = json.load(json_file)
    except IOError:
        raise ImportError

    return return_json


def get_author_str(json_i):
    """
    Returns formatted Author String
    """
    author_str = ""
    try:
        num_authors = len(json_i["author"])
        for j, author_json in enumerate(json_i["author"]):
            if j == num_authors - 1 and num_authors > 1:
                author_str += " and "
            elif j > 0:
                author_str += ", "

            author_str += (
                transform_given(author_json["given"]) + " " + author_json["family"]
            )
    except KeyError:
        num_authors = len(json_i["authors"])
        for j, author_json in enumerate(json_i["authors"]):
            if j == num_authors - 1 and num_authors > 1:
                author_str += " and "
            elif j > 0:
                author_str += ", "

            author_str += (
                transform_given(author_json["firstName"])
                + " "
                + author_json["lastName"]
            )
    return author_str + ","


def transform_given(name):
    """
    Formats first and middle name to APA intials
    """
    name = name.rstrip(".")
    name = name.split(" ")
    name = [subname.split("-") for subname in name]
    name = [[part[0] + "." for part in subname] for subname in name]
    name = " ".join(["-".join(subname) for subname in name])
    return name


def get_journal_str(json_i):
    j_string = '<span class="journal">'
    try:
        j_string += json_i["container-title"].strip()
    except KeyError:
        j_string += json_i["container-title-short"].strip()
    j_string += " </span>"
    return j_string


def get_vol_str(json_i):
    try:
        return '<span class="vol">' + json_i["volume"] + ", </span>"
    except KeyError:
        return ""


def get_page_str(json_i):
    p_string = '<span class="pages">'
    try:
        p_string += json_i["page"]
    except KeyError:
        try:
            p_string += json_i["article-number"]
        except KeyError:
            return ""
    p_string += " </span>"

    return p_string


def get_year_str(json_i):
    return f'<span class="year">({json_i["published"]["date-parts"][0][0]})</span>'


def get_linked_title(json_i):
    url = json_i["URL"]
    title = json_i["title"]
    return f'<span class="title"><a href="{url}"> {title}</a>. </span>'


def format_article(json_i):
    """
    Generates the string for the webpage

    param: json_i json for a single article

    return: formatted string
    """
    article_i_str = ""
    article_i_str += get_author_str(json_i)
    article_i_str += get_linked_title(json_i)
    article_i_str += get_journal_str(json_i)
    article_i_str += get_vol_str(json_i)
    article_i_str += get_page_str(json_i)
    article_i_str += get_year_str(json_i)
    article_i_str += "."

    return article_i_str


if __name__ == "__main__":
    main()

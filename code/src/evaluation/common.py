"""Shared setup for the evaluation scripts.

Evaluation data lives in its own Solr core (default `memorylane_eval`) under the
user id `eval`, so benchmark documents never mix with real users' pages. Create
the core first with: CORE_NAME=memorylane_eval ./scripts/setup_solr.sh
"""
import argparse

from backend.config import SOLR_URL
from backend.solr_client import SolrClient
from scripts.reindex import solr_base_from_url

EVAL_USER_ID = "eval"
DEFAULT_EVAL_CORE = "memorylane_eval"


def add_core_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--core", default=DEFAULT_EVAL_CORE,
                        help=f"Solr core holding evaluation data (default: {DEFAULT_EVAL_CORE})")
    parser.add_argument("--solr-base", default=solr_base_from_url(SOLR_URL),
                        help="Solr base URL (default: derived from SOLR_URL)")
    parser.add_argument("--user-id", default=EVAL_USER_ID,
                        help=f"User id the evaluation data is stored under (default: {EVAL_USER_ID})")


def eval_solr(args) -> SolrClient:
    solr = SolrClient(f"{args.solr_base.rstrip('/')}/{args.core}")
    if not solr.ping():
        raise SystemExit(
            f"Evaluation core not reachable: {solr.base_url}\n"
            f"Create it with: CORE_NAME={args.core} ./scripts/setup_solr.sh"
        )
    return solr

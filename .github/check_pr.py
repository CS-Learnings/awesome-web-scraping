#!/usr/bin/env python3
import json
import os
import re
import sys
from dataclasses import dataclass

from urllib3 import PoolManager

BAN_WORDS = [
    "ai",
    "mcp",
    "apify",
]

type BanRexList = list[tuple[str, re.Pattern[str]]]


@dataclass
class Event:
    token: str
    repo_owner: str
    repo_name: str
    pr_number: int


class GithubApiClient:
    def __init__(self, token: str) -> None:
        self.net = PoolManager()
        self.token = token

    def get_headers(self) -> dict[str, str]:
        return {
            "Authorization": "Bearer {}".format(self.token),
            "Accept": "application/vnd.github.v3+json",
        }


def build_ban_rex_list() -> BanRexList:
    ret = []
    for word in BAN_WORDS:
        ret.append((word, re.compile(r"\b{}\b".format(word), re.IGNORECASE)))
    return ret


def find_ban_word_match(
    pr_title: str, pr_body: str, ban_rex_list: BanRexList
) -> tuple[str, str] | tuple[None, None]:
    for ban_word, ban_rex in ban_rex_list:
        if ban_rex.search(pr_title):
            return ban_word, "title"
        if ban_rex.search(pr_body):
            return ban_word, "body"
    return None, None


def reject_pr(
    api: GithubApiClient,
    event: Event,
    reason: str,
    scope: str,
) -> None:
    comment_url = (
        f"https://api.github.com/repos/{event.repo_owner}/{event.repo_name}"
        f"/issues/{event.pr_number}/comments"
    )
    comment_body = (
        "This pull request has been automatically rejected because its {}"
        ' contains the restricted word "{}". Please see the CONTRIBUTING.md document'
        " for a list of disallowed content in this repository.".format(scope, reason)
    )
    print(comment_body)
    api.net.request(
        "POST",
        comment_url,
        headers=api.get_headers(),
        body=json.dumps({"body": comment_body}),
    )
    close_url = (
        f"https://api.github.com/repos/{event.repo_owner}/{event.repo_name}"
        f"/pulls/{event.pr_number}"
    )
    api.net.request(
        "PATCH",
        close_url,
        headers=api.get_headers(),
        body=json.dumps({"state": "closed"}),
    )


def check_pull_request(api: GithubApiClient, event: Event) -> None:
    pr_url = (
        f"https://api.github.com/repos/{event.repo_owner}/{event.repo_name}"
        f"/pulls/{event.pr_number}"
    )
    resp = api.net.request("GET", pr_url, headers=api.get_headers())
    if resp.status >= 400:
        raise RuntimeError("Invalid HTTP response code: {}".format(resp.status))
    pr_details = json.loads(resp.data)
    match = find_ban_word_match(
        pr_details.get("title", "") or "",
        pr_details.get("body", "") or "",
        build_ban_rex_list(),
    )
    if match[0]:
        reject_pr(api, event, match[0], match[1])
        sys.exit(1)  # non‑zero exit to indicate failure
    print("Pull request is OK")


def get_env_var(name: str) -> str:
    try:
        val = os.environ[name]
    except KeyError:
        raise RuntimeError("Environment variable {} must be defined".format(name))
    val = val.strip()
    if not val:
        raise RuntimeError(
            "Environment variable {} must contain non-blank value".format(name)
        )
    return val


if __name__ == "__main__":
    event = Event(
        token=get_env_var("GITHUB_TOKEN"),
        repo_owner=get_env_var("GITHUB_REPOSITORY_OWNER"),
        repo_name=get_env_var("GITHUB_REPOSITORY_NAME"),
        pr_number=int(get_env_var("PR_NUMBER")),
    )
    check_pull_request(GithubApiClient(event.token), event)

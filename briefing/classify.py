"""Cheap keyword pre-sorting. The editor model makes the real judgment; this only narrows the pool."""
from __future__ import annotations

import re

BIO = re.compile(
    r"\b(protein\w*|gene|genes|genetic\w*|genom\w*|dna|rna|mrna|crispr|base edit\w*|prime edit\w*|"
    r"cells?|cellular|cancer\w*|tumou?r\w*|oncolog\w*|drugs?|fda|ema|clinical|trials?|vaccin\w*|"
    r"antibod\w*|antibiotic\w*|bacteri\w*|virus\w*|viral|microb\w*|pathogen\w*|neuro\w*|brains?|"
    r"biolog\w*|biotech\w*|pharma\w*|disease\w*|alzheimer\w*|parkinson\w*|obesity|glp-1|diabet\w*|"
    r"immun\w*|enzym\w*|molecul\w*|evolution\w*|species|mice|mouse|patients?|medic\w*|organoid\w*|"
    r"stem cell\w*|embryo\w*|aging|ageing|longevity|biomarker\w*|sequenc\w*|transcript\w*|"
    r"single-cell|metabol\w*|microbiome|epigen\w*|chromosom\w*|ribosom\w*|peptide\w*|"
    r"gene therap\w*|cell therap\w*|biosecurity|epidemi\w*|pandemic\w*|health)\b",
    re.I,
)

AI = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|llms?|gpt[-\w.]*|chatgpt|claude|gemini|openai|anthropic|"
    r"deepmind|machine learning|deep learning|neural net\w*|transformers?|language models?|"
    r"foundation models?|diffusion models?|reinforcement learning|agentic|ai agents?|chatbots?|"
    r"llama|mistral|qwen|deepseek|grok|copilot|alphafold\w*|embedding\w*|inference|fine-tun\w*)\b",
    re.I,
)

SCIENCE = re.compile(
    r"\b(physic\w*|quantum|astronom\w*|telescope\w*|planet\w*|exoplanet\w*|galax\w*|cosmolog\w*|"
    r"black holes?|chemist\w*|materials?|superconduct\w*|fusion|climate|geolog\w*|mathemat\w*|"
    r"theorem|conjecture|proof|archaeolog\w*|fossil\w*|dinosaur\w*|paleont\w*|nasa|particle\w*|"
    r"scien\w*|researchers?|study finds|discover\w*|breakthrough)\b",
    re.I,
)

SCIENCE_DOMAINS = (
    "nature.com", "science.org", "cell.com", "nejm.org", "thelancet.com", "biorxiv.org", "medrxiv.org",
    "arxiv.org", "quantamagazine.org", "pnas.org", "sciencedaily.com", "newscientist.com",
    "sciencenews.org", "phys.org", "eurekalert.org", "statnews.com", "plos.org", "elifesciences.org",
)

BIO_DOMAINS = ("biorxiv.org", "medrxiv.org", "nejm.org", "thelancet.com", "cell.com", "statnews.com",
               "fiercebiotech.com", "endpoints.news", "biopharmadive.com", "genengnews.com")


def has_bio(text: str) -> bool:
    return bool(BIO.search(text or ""))


def has_ai(text: str) -> bool:
    return bool(AI.search(text or ""))


def has_science(text: str) -> bool:
    return bool(SCIENCE.search(text or ""))


def classify_story(title: str, domain: str) -> str | None:
    """Best-guess category for a Hacker News story, or None if it looks off-topic."""
    bio = has_bio(title) or domain.endswith(BIO_DOMAINS)
    ai = has_ai(title)
    sci = has_science(title) or domain.endswith(SCIENCE_DOMAINS)
    if ai and bio:
        return "ai_for_bio_med"
    if ai:
        return "ai_general"
    if bio:
        return "bio_biomed_research"
    if sci:
        return "science_breakthroughs"
    return None

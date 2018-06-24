import re
import sys
import nltk
import requests_cache
import grequests
import urllib.parse
import os
import json
import glob
import webbrowser
from time import sleep
from bs4 import BeautifulSoup

class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class weights:
    GOOGLE_SUMMARY_ANSWER_COUNT = 200
    NUM_GOOGLE_RESULTS = 100
    WIKIPEDIA_PAGE_QUESTION_COUNT = 100
    W1 = 200
    W2 = 100
    W3 = 100

# Build set of answers from raw data
def build_answers(raw_answers):
    answers = {
        'A': raw_answers[0]['text'],
        'B': raw_answers[1]['text'],
        'C': raw_answers[2]['text']
    }
    return answers

# Get answer predictions
def predict_answers(data, answers):

    confidence = {
        'A': 0,
        'B': 0,
        'C': 0
    }
    question = data.get('question')

    if not data.get('is_testing', False):
        webbrowser.open("http://google.com/search?q="+question)

    print('------------ %s %s | %s ------------' % ('QUESTION', data.get('questionNumber'), data.get('category')))
    print(colors.BOLD + question + colors.ENDC)
    print('------------ %s ------------' % 'ANSWERS')
    print(answers)
    print('------------------------')

    # Run confidence finding methods
    confidence_1 = method_1(question, answers)
    confidence_2 = method_2(question, answers)
    confidence_3 = method_3(question, answers)

    # Apply weights to confidences
    confidence_1 = {k: v*weights.W1 for k, v in confidence_1.items()}
    confidence_2 = {k: v*weights.W2 for k, v in confidence_2.items()}
    confidence_3 = {k: v*weights.W3 for k, v in confidence_3.items()}

    #Combine weightings to get overall confidence
    total_occurrences = sum(confidence_1.values()) + sum(confidence_2.values()) + sum(confidence_3.values())
    overall_confidence = {"A":0,"B":0,"C":0}
    for n in overall_confidence.items():
        overall_confidence[n[0]] = int((confidence_1[n[0]]+confidence_2[n[0]]+confidence_3[n[0]])/total_occurrences * 100) if total_occurrences else 0

    #Calculate prediction
    prediction = min(overall_confidence, key=overall_confidence.get) if 'NOT' in question or 'NEVER' in question else max(overall_confidence, key=overall_confidence.get)
    total_occurrences = sum(overall_confidence.values())
    for n, likelihood in overall_confidence.items():
        result = 'Answer %s: %s - %s%%' % (n, answers[n], likelihood)
        print(colors.BOLD + result + colors.ENDC if n == prediction else result)

    return (prediction if overall_confidence[prediction] else None, overall_confidence)


# METHOD 1: Find answer in Google search result descriptions
def method_1(question, answers):

    session = requests_cache.CachedSession('query_cache')
    google_responses = grequests.map([grequests.get('https://www.google.co.uk/search?q=' + urllib.parse.quote_plus(question), session=session)])
    response = google_responses[:1][0]

    occurrences = {'A': 0, 'B': 0, 'C': 0}
    confidence = {'A': 0, 'B': 0, 'C': 0}
    soup = BeautifulSoup(response.text, "html5lib")

    # Check for rate limiting page
    if '/sorry/index?continue=' in response.url:
        sys.exit('ERROR: Google rate limiting detected.')

    # Get search descriptions
    results = ''
    for g in soup.find_all(class_='st'):
        results += " " + g.text
    cleaned_results = results.strip().replace('\n','')
    results_words = get_raw_words(cleaned_results)

    # Find answer words in search descriptions
    for n, answer in answers.items():
        answer_words = get_raw_words(answer)
        occurrences[n] += results_words.count(answer_words)

    print("Count: %s%s%s" % (colors.BOLD, occurrences, colors.ENDC))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] = int(count/total_occurrences * 100) if total_occurrences else 0

    return confidence


# METHOD 2: Compare number of results found by Google
def method_2(question, answers):

    session = requests_cache.CachedSession('query_cache')
    queries = ['%s "%s"' % (question, answer) for answer in answers.values()]
    responses = grequests.map([grequests.get('https://www.google.co.uk/search?q=' + urllib.parse.quote_plus(q), session=session) for q in queries])

    occurrences = {'A': 0, 'B': 0, 'C': 0}
    confidence = {'A': 0, 'B': 0, 'C': 0}

    # Loop through search results
    for n, response in enumerate(responses):
        soup = BeautifulSoup(response.text, "html5lib")

        # Check for rate limiting page
        if '/sorry/index?continue=' in response.url:
            sys.exit('ERROR: Google rate limiting detected.')

        if soup.find(id='resultStats'):
            results_count_text = soup.find(id='resultStats').text.replace(',', '')
            if len(results_count_text) != 0 and len(re.findall(r'\d+', results_count_text)) != 0:
                results_count = re.findall(r'\d+', results_count_text)[0]
                occurrences[chr(65 + n)] += int(results_count)

        print("%s" % response.url)

    print("Search Results: %s%s%s" % (colors.BOLD, occurrences, colors.ENDC))

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] += int(count/total_occurrences * 100) if total_occurrences else 0

    return confidence


# METHOD 3: Find question words in wikipedia pages
def method_3(question, answers):

    session = requests_cache.CachedSession('query_cache')
    responses = grequests.map(build_wikipedia_queries(question, answers, session=session))
    occurrences = {'A': 0, 'B': 0, 'C': 0}
    confidence = {'A': 0, 'B': 0, 'C': 0}

    # Get nouns from question words
    question_words = get_raw_words(question)
    question_nouns = get_text_nouns(question_words).split(' ')

    # Loop through wikipedia results
    for n, response in enumerate(responses):

        # Check for unresolved Wikipedia link
        if 'Special:Search' in response.url:
            return confidence

        # Get wikipedia page text elements
        results = ''
        soup = BeautifulSoup(response.text, "html5lib")
        for g in soup.find_all('p'):
            results += " " + g.text
        cleaned_results = results.strip().replace('\n','')
        results_words = get_raw_words(cleaned_results)

        # Find question words on wikipedia page
        occurrences_list = find_keywords(question_nouns, results_words)
        occurrences[chr(65 + n)] += sum(occurrences_list)

    # Calculate confidence
    total_occurrences = sum(occurrences.values())
    for n, count in occurrences.items():
        confidence[n] += int(count/total_occurrences * 100) if total_occurrences else 0

    return confidence


# Find keywords in specified data
def find_keywords(keywords, data):
    words_found = []
    for keyword in keywords:
        if len(keyword) > 2:
            if keyword in data and keyword not in words_found:
                words_found.append(data.count(keyword))
    return words_found


# Get nouns from text
def get_text_nouns(input):
    response = ''
    for (word, tag) in nltk.pos_tag(nltk.word_tokenize(input)):
        if tag.startswith('NN') or tag.startswith('NNP'):
            response += word + ' '
    return response.strip()


# Extract raw words from data
def get_raw_words(data):
    data = re.sub('[^\w ]', '' , data)
    words = data.replace('  ' , ' ').lower()
    return words

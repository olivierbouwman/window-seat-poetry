# Window Seat Poetry

Play poetry relevant to the places you're seeing out the window on your flight.

## API Endpoint

The Poetry Foundation GraphQL API is available at:
```
https://www.poetryfoundation.org/proxy/graphql
```

## API Requests

### Fetching Authors

Use this GraphQL query to retrieve author information:

```json
{
  "operationName": "SearchPoetEntries",
  "query": "query SearchPoetEntries($limit: Int = 1000, $offset: Int = 0, $orderBy: String = \"postDate DESC\", $relatedTo: [EntryCriteriaInput], $search: String, $birthYear: [QueryArgument]) {\n  entries(\n    section: \"authors\"\n    limit: $limit\n    offset: $offset\n    orderBy: $orderBy\n    relatedToEntries: $relatedTo\n    search: $search\n    isPoet: true\n    birthYear: $birthYear\n  ) {\n    ...EntryCommon\n    ... on authors_default_Entry {\n      birthYear\n      deathYear\n      foundationBio\n      galeBio\n      poetryBio\n      polBio\n      }\n    }\n  count: entryCount(\n    section: \"authors\"\n    relatedToEntries: $relatedTo\n    search: $search\n    isPoet: true\n    birthYear: $birthYear\n  )\n}\n\nfragment EntryCommon on EntryInterface {\n  id\n\n  title\n  url\n  }",
  "variables": {
    "limit": 1000,
    "offset": 0,
    "orderBy": "postDate DESC",
    "relatedTo": null,
    "search": null,
    "birthYear": null
  }
}
```

### Fetching Poems

Use this GraphQL query to retrieve poem content:

```json
{
  "operationName": "SearchEntries",
  "query": "query SearchEntries($section: [String], $limit: Int = 1000, $offset: Int = 0, $orderBy: String = \"postDate DESC\") {\n  entries(section: $section, limit: $limit, offset: $offset, orderBy: $orderBy) {\n    id\n    title\n    url\n    body\n    authors {\n      id\n      }\n    audioVersion {\n      audioFile {\n        url\n}}\n  }\n  count: entryCount(section: $section)\n}",
  "variables": {
    "section": [
      "poems"
    ],
    "limit": 1000,
    "offset": 0,
    "orderBy": "postDate DESC"
  }
}
```

## Usage

These queries can be used with Postman.
Add these headers:
```
"key":"Content-Type","value":"application/json"
"key":"Accept","value":"application/json"
```

## Python stuff

1. `python3 -m venv venv`
2. `source venv/bin/activate`
3. `pip install -r requirements.txt`

### poetryfoundation.sh
Used to download authors or poems to json files.

### import-authors.py
`export SUPABASE_DB_URL="postgres://username:password@host:port/database"`

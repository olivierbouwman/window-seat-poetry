#!/bin/bash
# Set your parameters
limit=1000
baseUrl="https://www.poetryfoundation.org/proxy/graphql"
authHeader="Authorization: Basic cGY6cGZwcml2YXRl"
outputDir="authors"
mkdir -p "$outputDir"

# Function to fetch a page given an offset value
fetch_page() {
    offset=$1
    # Build JSON payload with a heredoc.
    # Note: Within the heredoc, we escape quotes and newlines appropriately.
    json=$(cat <<EOF
{
  "operationName": "SearchPoetEntries",
  "query": "query SearchPoetEntries(\$limit: Int = 1000, \$offset: Int = 0, \$orderBy: String = \"postDate DESC\", \$relatedTo: [EntryCriteriaInput], \$search: String, \$birthYear: [QueryArgument]) {\n  entries(\n    section: \"authors\"\n    limit: \$limit\n    offset: \$offset\n    orderBy: \$orderBy\n    relatedToEntries: \$relatedTo\n    search: \$search\n    isPoet: true\n    birthYear: \$birthYear\n  ) {\n    ...EntryCommon\n    ... on authors_default_Entry {\n      birthYear\n      deathYear\n      foundationBio\n      galeBio\n      poetryBio\n      polBio\n      }\n    }\n  count: entryCount(\n    section: \"authors\"\n    relatedToEntries: \$relatedTo\n    search: \$search\n    isPoet: true\n    birthYear: \$birthYear\n  )\n}\n\nfragment EntryCommon on EntryInterface {\n  id\n\n  title\n  url\n  }",
  "variables": {
    "limit": 1000,
    "offset": $offset,
    "orderBy": "postDate DESC",
    "relatedTo": null,
    "search": null,
    "birthYear": null
  }
}
EOF
)
    # Perform the curl request and output the JSON result silently.
    curl --silent --location "$baseUrl" \
      --header "Content-Type: application/json" \
      --header "Accept: application/json" \
      --header "$authHeader" \
      --data "$json"
}

# First, fetch the first page (offset=0) to get the total count.
echo "Fetching initial page..."
firstPage=$(fetch_page 0)
echo "$firstPage" > "$outputDir/page_0.json"

# Extract the total count from the returned JSON (using jq)
total=$(echo "$firstPage" | jq '.data.count')
echo "Total authors found: $total"

# Loop over pages (increment offset by $limit for each)
offset=$limit
while [ $offset -lt $total ]; do
    echo "Fetching offset $offset..."
    page=$(fetch_page $offset)
    # Save the result to a file named by the offset value.
    echo "$page" > "$outputDir/page_${offset}.json"
    offset=$(( offset + limit ))
done

echo "All pages have been saved in the directory '$outputDir'."

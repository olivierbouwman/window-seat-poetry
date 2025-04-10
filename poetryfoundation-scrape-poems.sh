#!/bin/bash
# Set your parameters
limit=1000
baseUrl="https://www.poetryfoundation.org/proxy/graphql"
authHeader="Authorization: Basic cGY6cGZwcml2YXRl"
outputDir="poems"
mkdir -p "$outputDir"

# Function to fetch a page given an offset value
fetch_page() {
    offset=$1
    # Build JSON payload with a heredoc.
    # Note: Within the heredoc, we escape quotes and newlines appropriately.
    json=$(cat <<EOF
{
  "operationName": "SearchEntries",
  "query": "query SearchEntries(\$section: [String], \$limit: Int = 1000, \$offset: Int = 0, \$orderBy: String = \"postDate DESC\") {\n  entries(section: \$section, limit: \$limit, offset: \$offset, orderBy: \$orderBy) {\n    id\n    title\n    url\n    body\n    authors {\n      id\n      }\n    audioVersion {\n      audioFile {\n        url\n}}\n  }\n  count: entryCount(section: \$section)\n}",
  "variables": {
    "section": [
      "poems"
    ],
    "limit": 1000,
    "offset": $offset,
    "orderBy": "postDate DESC"
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
echo "Total poems found: $total"

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

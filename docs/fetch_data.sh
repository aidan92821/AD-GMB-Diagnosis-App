#!/bin/zsh
set -euo pipefail

# make sure you have edirect (brew install edirect)
# check it worked with esearch -version

# get BioProject ID and number runs from command line
BIOPROJECT="$1"
N_RUNS="$2"

# get N_RUNS run IDs from BIOPROJECT into a txt file
cd ../data/srr_ids
esearch -db sra -query "$BIOPROJECT" \
  | efetch -format runinfo \
  | cut -d ',' -f 1 \
  | grep SRR \
  | head -n "$N_RUNS" \
  > "${BIOPROJECT}_srr_ids.txt"

if [ ! -s "${BIOPROJECT}_srr_ids.txt" ]; then
    echo "Error: No SRR runs found for $BIOPROJECT"
    exit 1
fi

# fetch runs and convert to fastq
echo "fetching runs and converting to fastq"
cd ../fastq_files/
mkdir -p "$BIOPROJECT"
cd "$BIOPROJECT"

while read srr; do
  fasterq-dump "$srr" --split-files --threads 8
done < "../../srr_ids/${BIOPROJECT}_srr_ids.txt"

# check for occurence of paired ends
if [[ -f *_2.fastq ]]; then
  # create the manifest.tsv file for qiime2 with paired ends
  echo "creating manifest file"
  mkdir -p "../../qiime_files/${BIOPROJECT}"
  touch "../../qiime_files/${BIOPROJECT}/manifest.tsv"

  printf "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n" > "../../qiime_files/${BIOPROJECT}/manifest.tsv"
  for f in *_1.fastq; do
    srr=$(basename "$f" _1.fastq)
    printf "%s\t%s\t%s\n" \
      "$srr" \
      "$(pwd)/${srr}_1.fastq" \
      "$(pwd)/${srr}_2.fastq" \
      >> "../../qiime_files/${BIOPROJECT}/manifest.tsv"
  done
  echo "done"
else
# create the manifest.tsv file for qiime2 with single ends
  echo "creating manifest file"
  mkdir -p "../../qiime_files/${BIOPROJECT}"
  touch "../../qiime_files/${BIOPROJECT}/manifest.tsv"

  printf "sample-id\tabsolute-filepath\n" > "../../qiime_files/${BIOPROJECT}/manifest.tsv"
  for f in *.fastq; do
    srr=$(basename "$f" .fastq)
    printf "%s\t%s\n" \
      "$srr" \
      "$(pwd)/${srr}.fastq" \
      >> "../../qiime_files/${BIOPROJECT}/manifest.tsv"
  done
  echo "done"
fi
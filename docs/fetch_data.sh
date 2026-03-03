#!/bin/zsh

# make sure you have edirect (brew install edirect)
# check it worked with esearch -version

# get all run IDs from study PRJNA1334232 into a txt file
cd ../data
esearch -db sra -query PRJNA1334232 | efetch -format runinfo | cut -d ',' -f 1 | grep SRR > srr_ids.txt

# fetch runs and convert to fastq (paired-end)
echo "fetching runs and converting to fastq"
cd fastq_files

while read srr; do
  fasterq-dump $srr --split-files --threads 8
done < ../srr_ids.txt

echo "finished"

# create the manifest.tsv file for qiime2
echo "creating manifest file"

printf "sample-id\tforward-absolute-filepath\treverse-absolute-filepath\n" >> ../qiime_files/manifest.tsv
for f in *_1.fastq; do
  srr=$(basename "$f" _1.fastq)
  printf "%s\t%s\t%s\n" \
    "$srr" \
    "$(pwd)/${srr}_1.fastq" \
    "$(pwd)/${srr}_2.fastq" \
    >> qiime_files/manifest.tsv
done
echo "done"
SELECT author, title, url, mergedAt, mergeCommit
FROM prs
WHERE
baseRefName IN('main', 'master')
AND NOT isDraft
AND (
	(files LIKE '%pkg/daemon%' OR files LIKE '%pkg/controller/node%' OR files LIKE '%pkg/controller/build%' OR files LIKE '%test/e2e-ocl%' OR files LIKE '%devex%' OR files LIKE '%hack%') AND
	((body LIKE '%OCB%' OR body LIKE '%OCL%' OR body LIKE '%layer%' OR body LIKE '%build%' OR body LIKE '%helper%' OR body LIKE '%devex%' OR body LIKE '%scripts%') OR (title LIKE '%OCB%' OR title LIKE '%OCL%' OR title LIKE '%layer%' OR title LIKE '%build%' OR title LIKE '%helper%' OR title LIKE '%devex%' OR title LIKE '%scripts%'))
)
AND state = 'MERGED'
AND DATE(mergedAt) BETWEEN '2024-11-22' AND date('now') AND (title NOT LIKE '%kube bump%' AND title NOT LIKE '%add RHEL variant%')
ORDER BY mergedAt DESC;

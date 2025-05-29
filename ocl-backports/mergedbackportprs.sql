SELECT author, title, url, mergedAt, baseRefName
FROM prs
WHERE baseRefName NOT IN('master', 'main')
AND NOT isDraft
AND (
	(files LIKE '%pkg/daemon%' OR files LIKE '%pkg/controller/node%' OR files LIKE '%pkg/controller/build%' OR files LIKE '%test/e2e-ocl%') AND
	((body LIKE '%OCB%' OR body LIKE '%OCL%' OR body LIKE '%layer%' OR body LIKE '%build%') OR (title LIKE '%OCB%' OR title LIKE '%OCL%' OR title LIKE '%layer%' OR title LIKE '%build%'))
)
AND state = 'MERGED'
AND DATE(mergedAt) BETWEEN '2024-11-22' AND date('now')
ORDER BY mergedAt DESC;

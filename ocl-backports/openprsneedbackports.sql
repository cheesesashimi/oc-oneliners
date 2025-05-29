SELECT author, title, url
FROM prs
WHERE
baseRefName IN('main', 'master')
AND NOT isDraft
AND (
	(files LIKE '%pkg/daemon%' OR files LIKE '%pkg/controller/node%' OR files LIKE '%pkg/controller/build%' OR files LIKE '%test/e2e-ocl%') AND
	((body LIKE '%OCB%' OR body LIKE '%OCL%' OR body LIKE '%layer%' OR body LIKE '%build%') OR (title LIKE '%OCB%' OR title LIKE '%OCL%' OR title LIKE '%layer%' OR title LIKE '%build%'))
)
AND state = 'OPEN';

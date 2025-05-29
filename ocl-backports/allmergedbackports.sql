SELECT author, title, url, mergedAt
FROM prs
WHERE state = 'MERGED'
AND DATE(mergedAt) BETWEEN '2024-11-22' AND date('now')
AND author IN(
	'openshift-bot',
	'openshift-cherrypick-robot'
)
ORDER BY mergedAt DESC;

SELECT author, title, url, mergedAt
FROM prs
WHERE state = 'MERGED'
AND DATE(mergedAt) BETWEEN '2024-11-22' AND date('now')
AND author IN(
	'LorbusChris',
	'RishabhSaini',
	'cheesesashimi',
	'djoshy',
	'dkhater-redhat',
	'isabella-janssen',
	'pablintino',
	'sergiordlr',
	'umohnani8',
	'yuqi-zhang'
)
ORDER BY mergedAt DESC;

-- E1 — structure recovery against a real production monorepo.
-- Produces the numbers in ../../findings/001-structure-recovery.md.
--
-- RECOVERED, NOT RECONSTRUCTED. Every statement below is the one that ran on
-- 2026-08-02, recovered from the session transcript rather than rewritten from
-- the finding's prose. Two disclosed changes, neither of which touches a query:
--
--   1. The subproject filter was a literal directory name inside a private
--      repository. It is now :subproject, supplied by run.sh. The finding calls
--      it "the largest subproject" and never names it either.
--   2. The database path was a literal path on the author's laptop. run.sh
--      takes it as a required argument and opens it read-only.
--
-- WHAT THIS CANNOT DO. It cannot reproduce a single number in finding 001. The
-- target is a private production monorepo that is deliberately not vendored and
-- not copied, and its analysis index is a 215 MB artifact built roughly five
-- weeks before the measurement. There is nothing to point this at. See README.md
-- for why it is committed anyway.
--
-- Reported values are quoted per block as "returned 2026-08-02". They are
-- properties of one index at one moment and are not targets.
--
-- Schema, as this index actually shapes it — three of the first attempts on
-- 2026-08-02 guessed wrong and returned nothing, and the corrected forms are the
-- ones below:
--
--   nodes(id, kind, name, file_path, start_line, signature, return_type,
--         docstring, language, ...)          -- file_path is on the node; there
--                                            -- is no usable nodes.file_id join
--   edges(kind, source, target, metadata)    -- NOT source_id / target_id
--   files(path, language, ...)
--   project_metadata(...)
--
-- A route node's name is the string "VERB /path", or a bare path when the
-- extractor found no verb. Every classification below keys off that string.


-- ---------------------------------------------------------------------------
-- 1. Scale, and what the index says about itself.
--    §Target: 4,496 files, 63,783 nodes, 207,722 edges; index format v1.1.1,
--    extraction version 24.
--    Row counts were taken by iterating .tables and counting each; the two that
--    the finding quotes are below.
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS nodes FROM nodes;
SELECT COUNT(*) AS edges FROM edges;
SELECT * FROM project_metadata;


-- ---------------------------------------------------------------------------
-- 2. Language mix.
--    §Target: 96% TypeScript/TSX — 3,029 .ts + 1,032 .tsx + 270 .js against 152
--    Python files.
-- ---------------------------------------------------------------------------
SELECT language, COUNT(*) c FROM files GROUP BY language ORDER BY c DESC LIMIT 15;


-- ---------------------------------------------------------------------------
-- 3. Node and edge vocabularies.
--    §3: the edge kinds are calls, contains, references, imports, instantiates,
--    extends, implements, decorates — and there is no route->handler kind among
--    them. That absence is the whole of §3's first claim, and it is read off
--    this query rather than from documentation.
--    Node kinds gave the 1,161 routes the rest of the finding works from.
-- ---------------------------------------------------------------------------
SELECT kind, COUNT(*) c FROM nodes GROUP BY kind ORDER BY c DESC;
SELECT kind, COUNT(*) c FROM edges GROUP BY kind ORDER BY c DESC;


-- ---------------------------------------------------------------------------
-- 4. THE HEADLINE. Route-extraction precision, repo-wide.
--    §1: of 1,161 route nodes, 866 real HTTP endpoints (74.6%), 137 middleware
--    (11.8%), 156 verb-less UI routes (13.4%), 2 wildcards (0.2%).
--
--    Read the classification before you quote the number. "Real HTTP endpoint"
--    is a prefix test on the node's name string, and "verb-less" is the absence
--    of a space in it. That is a property of how one extractor formats one
--    field, not of route extraction, which is exactly what finding 004 later
--    established the hard way when the same filter removed zero of 41 false
--    positives on a Python target. The retraction is visible in this query.
-- ---------------------------------------------------------------------------
SELECT
  SUM(CASE WHEN instr(name,' ')=0 THEN 1 ELSE 0 END) AS verbless_ui_routes,
  SUM(CASE WHEN name LIKE 'USE %' THEN 1 ELSE 0 END) AS middleware,
  SUM(CASE WHEN name LIKE 'ALL %' THEN 1 ELSE 0 END) AS wildcard,
  SUM(CASE WHEN name LIKE 'GET %' OR name LIKE 'POST %' OR name LIKE 'PUT %'
            OR name LIKE 'PATCH %' OR name LIKE 'DELETE %' THEN 1 ELSE 0 END)
      AS real_http_endpoints,
  COUNT(*) AS total
FROM nodes WHERE kind='route';


-- ---------------------------------------------------------------------------
-- 5. The server/client split inside the largest subproject.
--    §1: its server/ tree holds 425 route nodes with zero verb-less entries;
--    its client src/ tree holds 86 that are 100% verb-less.
--    This is the evidence that the pollution is one extractor filing React
--    Router paths under the same node kind as server endpoints.
-- ---------------------------------------------------------------------------
SELECT
  CASE
    WHEN file_path LIKE :subproject || '/server/%' THEN 'server/ (API)'
    WHEN file_path LIKE :subproject || '/src/%'    THEN 'src/ (client UI)'
    WHEN file_path LIKE :subproject || '/convex/%' THEN 'convex/'
    ELSE 'other'
  END AS area,
  COUNT(*) AS routes,
  SUM(CASE WHEN instr(name,' ')=0 THEN 1 ELSE 0 END) AS verbless,
  SUM(CASE WHEN name LIKE 'USE %' THEN 1 ELSE 0 END) AS middleware
FROM nodes WHERE kind='route' AND file_path LIKE :subproject || '/%'
GROUP BY area ORDER BY routes DESC;

-- Samples behind §1's "a login screen or an embed viewer" characterisation.
SELECT name, file_path, start_line FROM nodes
WHERE kind='route' AND file_path LIKE :subproject || '/%' AND instr(name,' ')=0
LIMIT 8;

SELECT name FROM nodes
WHERE kind='route' AND file_path LIKE :subproject || '/%' AND name LIKE 'POST %'
LIMIT 10;

-- Verb distribution, the weak effect-class proxy §"What this means" item 4 rejects.
SELECT substr(name,1,instr(name,' ')-1) AS verb, COUNT(*) c
FROM nodes WHERE kind='route' AND file_path LIKE :subproject || '/%'
GROUP BY verb ORDER BY c DESC;

SELECT kind, COUNT(*) c FROM nodes
WHERE file_path LIKE :subproject || '/%' GROUP BY kind ORDER BY c DESC LIMIT 12;


-- ---------------------------------------------------------------------------
-- 6. Contract metadata coverage by node kind.
--    §2's table: function 17,546 / 17,546 signatures / 0 return types / 5,438
--    docstrings; method 4,558 / 4,557 / 0 / 2,312; route 1,161 / 0 / 0 / 0;
--    interface 4,395; class 595; component 49.
--
--    Note the scope: seven kinds, not all 63,783 nodes. §2's stronger sentence,
--    "return_type is empty across all 63,783 nodes", is NOT this query. See the
--    Gaps table in README.md.
-- ---------------------------------------------------------------------------
SELECT kind,
       COUNT(*) AS total,
       SUM(CASE WHEN signature IS NOT NULL AND signature<>'' THEN 1 ELSE 0 END)
           AS with_signature,
       SUM(CASE WHEN return_type IS NOT NULL AND return_type<>'' THEN 1 ELSE 0 END)
           AS with_return_type,
       SUM(CASE WHEN docstring IS NOT NULL AND docstring<>'' THEN 1 ELSE 0 END)
           AS with_docstring
FROM nodes
WHERE kind IN ('route','function','method','class','interface','component','type_alias')
GROUP BY kind ORDER BY total DESC;

-- §2's "return types are partially recoverable from the signature text field".
SELECT signature FROM nodes
WHERE kind='function' AND file_path LIKE :subproject || '/%' AND signature<>''
LIMIT 8;


-- ---------------------------------------------------------------------------
-- 7. What routes are connected to.
--    §3: 1,995 outgoing calls, 144 references, 904 incoming calls; and 211 of
--    1,161 route nodes (18.2%) have no edges whatsoever.
--    The 211 is the complement of the third query here — 950 routes participate
--    in at least one edge — and is not itself a recorded query.
-- ---------------------------------------------------------------------------
SELECT e.kind, COUNT(*) FROM edges e JOIN nodes n ON e.source=n.id
WHERE n.kind='route' GROUP BY e.kind;

SELECT e.kind, COUNT(*) FROM edges e JOIN nodes n ON e.target=n.id
WHERE n.kind='route' GROUP BY e.kind;

SELECT COUNT(DISTINCT n.id) FROM nodes n
WHERE n.kind='route'
  AND (EXISTS(SELECT 1 FROM edges e WHERE e.source=n.id)
    OR EXISTS(SELECT 1 FROM edges e WHERE e.target=n.id));

-- Checked because handler identity could plausibly have been hiding in it. It
-- was not, which is why §3 concludes the handler must be inferred.
SELECT kind, metadata FROM edges
WHERE metadata IS NOT NULL AND metadata<>'' LIMIT 5;


-- ---------------------------------------------------------------------------
-- 8. THE BRIDGE. Route -> handler -> signature, across the 866 real endpoints.
--    §4's first table: 791 reach a typed handler (91.3%), 4 reach an untyped
--    one, 71 are dead ends (8.2%).
-- ---------------------------------------------------------------------------
WITH real_routes AS (
  SELECT id, name, file_path FROM nodes
  WHERE kind='route'
    AND (name LIKE 'GET %' OR name LIKE 'POST %' OR name LIKE 'PUT %'
      OR name LIKE 'PATCH %' OR name LIKE 'DELETE %')
),
bridged AS (
  SELECT r.id,
         COUNT(DISTINCT t.id) AS callee_fns,
         SUM(CASE WHEN t.signature IS NOT NULL AND t.signature<>''
                   AND t.signature<>'()' THEN 1 ELSE 0 END) AS typed_callees
  FROM real_routes r
  LEFT JOIN edges e ON e.source=r.id AND e.kind='calls'
  LEFT JOIN nodes t ON t.id=e.target AND t.kind IN ('function','method')
  GROUP BY r.id
)
SELECT COUNT(*) AS total_real_endpoints,
       SUM(CASE WHEN callee_fns=0 THEN 1 ELSE 0 END) AS no_handler_reachable,
       SUM(CASE WHEN callee_fns>0 THEN 1 ELSE 0 END) AS handler_reachable,
       SUM(CASE WHEN typed_callees>0 THEN 1 ELSE 0 END) AS reaches_TYPED_handler,
       ROUND(100.0*SUM(CASE WHEN typed_callees>0 THEN 1 ELSE 0 END)/COUNT(*),1)
           AS pct_typed
FROM bridged;


-- ---------------------------------------------------------------------------
-- 9. THE AMBIGUITY. Callees per endpoint.
--    §4's second table: 303 unambiguous, 409 with 2-4, 88 with 5-10, 6 with 11+,
--    60 dead ends. "Roughly 58% reach two or more callees" is (409+88+6)/866.
--
--    Two things are visible here that were not visible in the prose.
--
--    First, this query counts DISTINCT e.target over kind='calls' with NO filter
--    on the target's kind, while block 8 restricts callees to functions and
--    methods. That is why the same finding reports 71 dead ends in one table and
--    60 in the other, on the same 866 endpoints, without reconciling them.
--
--    Second, nothing here attempts to identify a handler. What is being counted
--    is call-graph fan-out — loggers, validators and serializers included, as
--    §4's own prose concedes. Finding 004 later measured zero ambiguity on a
--    Python target, because that extractor emits a direct route-to-handler edge
--    and this one does not. The 58% is a property of having to infer through
--    generic `calls` edges, and that is legible in the query text.
-- ---------------------------------------------------------------------------
WITH real_routes AS (
  SELECT id FROM nodes WHERE kind='route'
    AND (name LIKE 'GET %' OR name LIKE 'POST %' OR name LIKE 'PUT %'
      OR name LIKE 'PATCH %' OR name LIKE 'DELETE %')
)
SELECT CASE WHEN c=0 THEN '0 (dead end)' WHEN c=1 THEN '1 (unambiguous)'
            WHEN c BETWEEN 2 AND 4 THEN '2-4' WHEN c BETWEEN 5 AND 10 THEN '5-10'
            ELSE '11+' END AS callees,
       COUNT(*) AS endpoints
FROM (SELECT r.id, COUNT(DISTINCT e.target) c FROM real_routes r
      LEFT JOIN edges e ON e.source=r.id AND e.kind='calls' GROUP BY r.id)
GROUP BY callees ORDER BY endpoints DESC;

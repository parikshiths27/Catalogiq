import React, { useState, useEffect } from 'react';
import { Search, Loader2, Sparkles, Filter, ExternalLink, AlertCircle, Database, ShieldAlert, X, SlidersHorizontal, Info } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

interface AttributeItem {
  attribute_name: string;
  display_name: string;
  raw_value: string;
  unit?: string;
  confidence: number;
  status: string;
}

interface SearchResultItem {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  manufacturer: string;
  model?: string;
  quality_score: number;
  similarity_score?: number;
  keyword_score?: number;
  hybrid_score?: number;
  match_type?: string;
  ranking_priority?: number;
  query_intent?: string;
  matched_fields?: string[];
  status: string;
  commerce_description?: string;
  short_description?: string;
  features: string[];
  applications: string[];
  attributes: AttributeItem[];
}

interface SearchResponse {
  query: string;
  total: number;
  search_mode?: string;
  degraded_mode?: string | null;
  query_intent?: string | null;
  results: SearchResultItem[];
}

interface FacetCountItem {
  value: string;
  count: number;
}

interface QualityScoreRangeItem {
  label: string;
  min: number;
  max: number;
  count: number;
}

interface DynamicAttributeFacet {
  attribute_name: string;
  display_name: string;
  data_type: string;
  values: FacetCountItem[];
}

interface FacetPayload {
  categories: FacetCountItem[];
  brands: FacetCountItem[];
  subcategories: FacetCountItem[];
  statuses: FacetCountItem[];
  quality_score_ranges: QualityScoreRangeItem[];
  attributes: DynamicAttributeFacet[];
}

interface FacetSearchResponse {
  query: string;
  facets: FacetPayload;
}

export const SearchShell: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL State initialization
  const initialQuery = searchParams.get('q') || 'industrial induction motors around 10 kW';
  const initialCategory = searchParams.get('category') ? searchParams.get('category')!.split(',').filter(Boolean) : [];
  const initialBrand = searchParams.get('brand') ? searchParams.get('brand')!.split(',').filter(Boolean) : [];
  const initialStatus = searchParams.get('status') ? searchParams.get('status')!.split(',').filter(Boolean) : [];
  const initialMinQuality = searchParams.get('min_quality_score') ? parseFloat(searchParams.get('min_quality_score')!) : undefined;
  const initialMaxQuality = searchParams.get('max_quality_score') ? parseFloat(searchParams.get('max_quality_score')!) : undefined;
  const initialMode = searchParams.get('mode') || 'hybrid';

  const [query, setQuery] = useState<string>(initialQuery);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(initialCategory);
  const [selectedBrands, setSelectedBrands] = useState<string[]>(initialBrand);
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>(initialStatus);
  const [minQualityScore, setMinQualityScore] = useState<number | undefined>(initialMinQuality);
  const [maxQualityScore, setMaxQualityScore] = useState<number | undefined>(initialMaxQuality);
  const [searchMode, setSearchMode] = useState<string>(initialMode);
  const [limit, setLimit] = useState<number>(10);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchData, setSearchData] = useState<SearchResponse | null>(null);
  const [facetData, setFacetData] = useState<FacetPayload | null>(null);
  const [showFiltersSidebar, setShowFiltersSidebar] = useState<boolean>(true);
  const [expandedScoreId, setExpandedScoreId] = useState<string | null>(null);

  // Sync parameters with URL
  const syncUrlParams = (
    q: string,
    cats: string[],
    brs: string[],
    stats: string[],
    minQ?: number,
    maxQ?: number,
    modeStr?: string
  ) => {
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    if (cats.length) params.set('category', cats.join(','));
    if (brs.length) params.set('brand', brs.join(','));
    if (stats.length) params.set('status', stats.join(','));
    if (minQ !== undefined && !isNaN(minQ)) params.set('min_quality_score', minQ.toString());
    if (maxQ !== undefined && !isNaN(maxQ)) params.set('max_quality_score', maxQ.toString());
    if (modeStr) params.set('mode', modeStr);

    setSearchParams(params);
  };

  // Perform search and facet retrieval
  const handleSearch = async (
    overrideQuery?: string,
    overrideCats?: string[],
    overrideBrands?: string[],
    overrideStatuses?: string[],
    overrideMinQ?: number,
    overrideMaxQ?: number,
    overrideMode?: string
  ) => {
    const q = overrideQuery !== undefined ? overrideQuery : query;
    const cats = overrideCats !== undefined ? overrideCats : selectedCategories;
    const brs = overrideBrands !== undefined ? overrideBrands : selectedBrands;
    const stats = overrideStatuses !== undefined ? overrideStatuses : selectedStatuses;
    const minQ = overrideMinQ !== undefined ? overrideMinQ : minQualityScore;
    const maxQ = overrideMaxQ !== undefined ? overrideMaxQ : maxQualityScore;
    const m = overrideMode !== undefined ? overrideMode : searchMode;

    if (!q.trim()) return;

    setLoading(true);
    setError(null);
    syncUrlParams(q, cats, brs, stats, minQ, maxQ, m);

    try {
      // 1. Fetch Search Results
      const searchUrlParams = new URLSearchParams();
      searchUrlParams.append('q', q.trim());
      searchUrlParams.append('limit', limit.toString());
      if (cats.length) searchUrlParams.append('category', cats.join(','));
      if (brs.length) searchUrlParams.append('brand', brs.join(','));
      if (stats.length) searchUrlParams.append('status', stats.join(','));
      if (minQ !== undefined && !isNaN(minQ)) searchUrlParams.append('min_quality_score', minQ.toString());
      if (maxQ !== undefined && !isNaN(maxQ)) searchUrlParams.append('max_quality_score', maxQ.toString());
      if (m) searchUrlParams.append('mode', m);

      const res = await fetch(`/api/v1/search?${searchUrlParams.toString()}`);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Search failed with status ${res.status}`);
      }

      const data: SearchResponse = await res.json();
      setSearchData(data);

      // 2. Fetch Facets
      const facetUrlParams = new URLSearchParams();
      facetUrlParams.append('q', q.trim());
      if (cats.length) facetUrlParams.append('category', cats.join(','));
      if (brs.length) facetUrlParams.append('brand', brs.join(','));
      if (stats.length) facetUrlParams.append('status', stats.join(','));
      if (minQ !== undefined && !isNaN(minQ)) facetUrlParams.append('min_quality_score', minQ.toString());
      if (maxQ !== undefined && !isNaN(maxQ)) facetUrlParams.append('max_quality_score', maxQ.toString());

      const facetRes = await fetch(`/api/v1/search/facets?${facetUrlParams.toString()}`);
      if (facetRes.ok) {
        const fData: FacetSearchResponse = await facetRes.json();
        setFacetData(fData.facets);
      }
    } catch (err: any) {
      console.error('Search error:', err);
      setError(err.message || 'An error occurred while connecting to the search service.');
    } finally {
      setLoading(false);
    }
  };

  // Perform initial search on mount
  useEffect(() => {
    handleSearch();
  }, []);

  const toggleCategory = (cat: string) => {
    const next = selectedCategories.includes(cat)
      ? selectedCategories.filter((c) => c !== cat)
      : [...selectedCategories, cat];
    setSelectedCategories(next);
    handleSearch(query, next, selectedBrands, selectedStatuses, minQualityScore, maxQualityScore, searchMode);
  };

  const toggleBrand = (brand: string) => {
    const next = selectedBrands.includes(brand)
      ? selectedBrands.filter((b) => b !== brand)
      : [...selectedBrands, brand];
    setSelectedBrands(next);
    handleSearch(query, selectedCategories, next, selectedStatuses, minQualityScore, maxQualityScore, searchMode);
  };

  const toggleStatus = (st: string) => {
    const next = selectedStatuses.includes(st)
      ? selectedStatuses.filter((s) => s !== st)
      : [...selectedStatuses, st];
    setSelectedStatuses(next);
    handleSearch(query, selectedCategories, selectedBrands, next, minQualityScore, maxQualityScore, searchMode);
  };

  const handleClearAllFilters = () => {
    setSelectedCategories([]);
    setSelectedBrands([]);
    setSelectedStatuses([]);
    setMinQualityScore(undefined);
    setMaxQualityScore(undefined);
    handleSearch(query, [], [], [], undefined, undefined, searchMode);
  };

  const exampleQueries = [
    'industrial induction motors around 10 kW',
    'high RPM induction motors with IP55 protection',
    'motors suitable for continuous duty pumps',
    'MX500-230',
  ];

  const hasActiveFilters =
    selectedCategories.length > 0 ||
    selectedBrands.length > 0 ||
    selectedStatuses.length > 0 ||
    minQualityScore !== undefined ||
    maxQualityScore !== undefined;

  return (
    <div className="space-y-6 text-slate-100">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
            <Sparkles className="w-7 h-7 text-indigo-400" />
            <span>Catalog IQ Hybrid Search & Discovery</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Unified semantic, lexical keyword, and faceted filtering search across industrial product catalogs.
          </p>
        </div>

        {/* Mode Selector */}
        <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs self-start md:self-auto">
          {['hybrid', 'semantic', 'keyword'].map((m) => (
            <button
              key={m}
              onClick={() => {
                setSearchMode(m);
                handleSearch(query, selectedCategories, selectedBrands, selectedStatuses, minQualityScore, maxQualityScore, m);
              }}
              className={`px-3 py-1.5 rounded-md font-medium capitalize transition ${
                searchMode === m
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Search Input Bar & Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-5 h-5 text-slate-400 absolute left-4 top-3.5" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search by product name, SKU, model, or natural language specs..."
              className="w-full bg-slate-950 border border-slate-700 text-white rounded-lg pl-11 pr-4 py-3 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => handleSearch()}
              disabled={loading}
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-lg text-sm font-medium transition flex items-center justify-center gap-2 disabled:opacity-50 min-w-[120px]"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              <span>Search</span>
            </button>

            <button
              onClick={() => setShowFiltersSidebar(!showFiltersSidebar)}
              className={`px-4 py-3 rounded-lg border text-sm font-medium transition flex items-center gap-2 ${
                showFiltersSidebar
                  ? 'bg-slate-800 border-indigo-500 text-indigo-300'
                  : 'bg-slate-950 border-slate-700 text-slate-300 hover:bg-slate-800'
              }`}
            >
              <SlidersHorizontal className="w-4 h-4" />
              <span>Filters</span>
            </button>
          </div>
        </div>

        {/* Example Queries & Result Limit */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-300">Try searching:</span>
            {exampleQueries.map((eq, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setQuery(eq);
                  handleSearch(eq);
                }}
                className="bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-white px-3 py-1 rounded-md border border-slate-800 transition"
              >
                {eq}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-slate-400">Page size:</span>
            <select
              value={limit}
              onChange={(e) => {
                const newLimit = parseInt(e.target.value, 10);
                setLimit(newLimit);
                handleSearch(query, selectedCategories, selectedBrands, selectedStatuses, minQualityScore, maxQualityScore, searchMode);
              }}
              className="bg-slate-950 border border-slate-700 text-slate-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>
        </div>
      </div>

      {/* Active Filter Chips Bar */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2 bg-slate-900/60 border border-slate-800 rounded-lg p-3 text-xs">
          <span className="font-medium text-slate-400 flex items-center gap-1">
            <Filter className="w-3.5 h-3.5 text-indigo-400" /> Active Filters:
          </span>

          {selectedCategories.map((c) => (
            <span key={c} className="bg-indigo-950 border border-indigo-700 text-indigo-200 px-2.5 py-1 rounded-full flex items-center gap-1">
              Cat: {c}
              <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => toggleCategory(c)} />
            </span>
          ))}

          {selectedBrands.map((b) => (
            <span key={b} className="bg-purple-950 border border-purple-700 text-purple-200 px-2.5 py-1 rounded-full flex items-center gap-1">
              Brand: {b}
              <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => toggleBrand(b)} />
            </span>
          ))}

          {selectedStatuses.map((s) => (
            <span key={s} className="bg-emerald-950 border border-emerald-700 text-emerald-200 px-2.5 py-1 rounded-full flex items-center gap-1">
              Status: {s}
              <X className="w-3 h-3 cursor-pointer hover:text-white" onClick={() => toggleStatus(s)} />
            </span>
          ))}

          {minQualityScore !== undefined && (
            <span className="bg-amber-950 border border-amber-700 text-amber-200 px-2.5 py-1 rounded-full flex items-center gap-1">
              Min Quality: {minQualityScore}%
              <X
                className="w-3 h-3 cursor-pointer hover:text-white"
                onClick={() => {
                  setMinQualityScore(undefined);
                  handleSearch(query, selectedCategories, selectedBrands, selectedStatuses, undefined, maxQualityScore, searchMode);
                }}
              />
            </span>
          )}

          <button onClick={handleClearAllFilters} className="text-slate-400 hover:text-white underline ml-auto text-xs">
            Clear All
          </button>
        </div>
      )}

      {/* Main Grid: Sidebar Filters + Results */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Sidebar Filters */}
        {showFiltersSidebar && (
          <div className="md:col-span-1 bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-6 self-start shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-semibold text-white flex items-center gap-2 text-sm">
                <Filter className="w-4 h-4 text-indigo-400" />
                <span>Facet Filters</span>
              </h3>
              {hasActiveFilters && (
                <button onClick={handleClearAllFilters} className="text-xs text-indigo-400 hover:text-indigo-300">
                  Reset
                </button>
              )}
            </div>

            {/* Category Facet */}
            {facetData?.categories && facetData.categories.length > 0 && (
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Category</label>
                <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                  {facetData.categories.map((item) => (
                    <label key={item.value} className="flex items-center justify-between text-xs text-slate-300 hover:text-white cursor-pointer py-1">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedCategories.includes(item.value)}
                          onChange={() => toggleCategory(item.value)}
                          className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="truncate max-w-[130px]">{item.value}</span>
                      </div>
                      <span className="bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono">{item.count}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Brand Facet */}
            {facetData?.brands && facetData.brands.length > 0 && (
              <div className="space-y-2 border-t border-slate-800 pt-3">
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Brand / Manufacturer</label>
                <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                  {facetData.brands.map((item) => (
                    <label key={item.value} className="flex items-center justify-between text-xs text-slate-300 hover:text-white cursor-pointer py-1">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedBrands.includes(item.value)}
                          onChange={() => toggleBrand(item.value)}
                          className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="truncate max-w-[130px]">{item.value}</span>
                      </div>
                      <span className="bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono">{item.count}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Status Facet */}
            {facetData?.statuses && facetData.statuses.length > 0 && (
              <div className="space-y-2 border-t border-slate-800 pt-3">
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Product Status</label>
                <div className="space-y-1.5">
                  {facetData.statuses.map((item) => (
                    <label key={item.value} className="flex items-center justify-between text-xs text-slate-300 hover:text-white cursor-pointer py-1">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedStatuses.includes(item.value)}
                          onChange={() => toggleStatus(item.value)}
                          className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="capitalize">{item.value}</span>
                      </div>
                      <span className="bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded text-[10px] font-mono">{item.count}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Quality Score Range Filter */}
            <div className="space-y-2 border-t border-slate-800 pt-3">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Min Quality Score</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={minQualityScore !== undefined ? minQualityScore : ''}
                  onChange={(e) => {
                    const val = e.target.value ? parseFloat(e.target.value) : undefined;
                    setMinQualityScore(val);
                    handleSearch(query, selectedCategories, selectedBrands, selectedStatuses, val, maxQualityScore, searchMode);
                  }}
                  placeholder="Min %"
                  className="w-full bg-slate-950 border border-slate-700 text-white rounded px-2 py-1.5 text-xs focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Dynamic Attributes Facets */}
            {facetData?.attributes && facetData.attributes.length > 0 && (
              <div className="space-y-4 border-t border-slate-800 pt-3">
                <label className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">Dynamic Specs</label>
                {facetData.attributes.map((attr) => (
                  <div key={attr.attribute_name} className="space-y-1.5">
                    <span className="text-[11px] font-medium text-slate-400">{attr.display_name}</span>
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                      {attr.values.slice(0, 5).map((valItem) => (
                        <div key={valItem.value} className="flex items-center justify-between text-xs text-slate-300 py-0.5">
                          <span className="truncate max-w-[120px]">{valItem.value}</span>
                          <span className="text-[10px] text-slate-500 font-mono">{valItem.count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Results Container */}
        <div className={showFiltersSidebar ? 'md:col-span-3' : 'md:col-span-4'}>
          {error && (
            <div className="bg-red-950/50 border border-red-800 rounded-xl p-4 text-red-300 flex items-start gap-3 mb-4">
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-sm">Search Failed</h4>
                <p className="text-xs text-red-300/80 mt-1">{error}</p>
              </div>
            </div>
          )}

          {searchData && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between text-xs text-slate-400 px-1 gap-2">
                <div className="flex items-center gap-2">
                  <span>
                    Found <strong className="text-white">{searchData.total}</strong> products matching query
                  </span>
                  {searchData.query_intent && (
                    <span className="bg-indigo-950 border border-indigo-700 text-indigo-300 px-2 py-0.5 rounded text-[11px] font-mono">
                      Intent: {searchData.query_intent}
                    </span>
                  )}
                </div>

                {searchData.degraded_mode && (
                  <span className="bg-amber-950 border border-amber-700 text-amber-300 px-2 py-0.5 rounded text-[11px] flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5" /> Degraded: {searchData.degraded_mode}
                  </span>
                )}
              </div>

              {searchData.results.length === 0 ? (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center space-y-3">
                  <Database className="w-10 h-10 text-slate-600 mx-auto" />
                  <h4 className="text-lg font-semibold text-slate-300">No Products Found</h4>
                  <p className="text-xs text-slate-500 max-w-md mx-auto">
                    No catalog items matched your current search query and filter criteria. Try adjusting your query or resetting active filters.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {searchData.results.map((item) => {
                    const isExpanded = expandedScoreId === item.product_id;
                    const matchLabel = item.match_type === 'exact'
                      ? 'Exact Match'
                      : item.match_type === 'hybrid'
                      ? 'Hybrid Match'
                      : item.match_type === 'keyword'
                      ? 'Keyword Match'
                      : 'Semantic Match';

                    const matchBadgeClass = item.match_type === 'exact'
                      ? 'bg-emerald-950 border-emerald-700 text-emerald-300'
                      : item.match_type === 'hybrid'
                      ? 'bg-indigo-950 border-indigo-700 text-indigo-300'
                      : item.match_type === 'keyword'
                      ? 'bg-purple-950 border-purple-700 text-purple-300'
                      : 'bg-blue-950 border-blue-700 text-blue-300';

                    return (
                      <div
                        key={item.product_id}
                        className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-5 shadow-lg transition space-y-3"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                          <div>
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3
                                className="text-base font-bold text-white hover:text-indigo-400 transition cursor-pointer"
                                onClick={() => navigate(`/products/${item.product_id}`)}
                              >
                                {item.product_name}
                              </h3>
                              <span className={`border text-[10px] px-2 py-0.5 rounded font-medium ${matchBadgeClass}`}>
                                {matchLabel}
                              </span>
                            </div>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400 mt-1">
                              <span>SKU: <strong className="text-slate-200">{item.sku}</strong></span>
                              <span>•</span>
                              <span>Brand: <strong className="text-slate-200">{item.manufacturer}</strong></span>
                              <span>•</span>
                              <span>Category: <strong className="text-indigo-300">{item.category}</strong></span>
                              {item.model && (
                                <>
                                  <span>•</span>
                                  <span>Model: <strong className="text-slate-200">{item.model}</strong></span>
                                </>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            <div className="text-right flex items-center gap-1">
                              <div>
                                <div className="text-[11px] text-slate-400">Relevance</div>
                                <div className="text-sm font-bold text-indigo-400">
                                  {((item.hybrid_score ?? item.similarity_score ?? item.keyword_score ?? 0) * 100).toFixed(0)}%
                                </div>
                              </div>
                              <button
                                onClick={() => setExpandedScoreId(isExpanded ? null : item.product_id)}
                                className="p-1 text-slate-400 hover:text-indigo-300 transition"
                                title="Toggle Score Breakdown"
                              >
                                <Info className="w-4 h-4" />
                              </button>
                            </div>

                            <button
                              onClick={() => navigate(`/products/${item.product_id}`)}
                              className="p-2 text-slate-400 hover:text-white bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-lg transition"
                              title="View Product Intelligence"
                            >
                              <ExternalLink className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        {/* Detailed Score Breakdown Popover */}
                        {isExpanded && (
                          <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs space-y-1.5 font-mono text-slate-300">
                            <div className="font-semibold text-indigo-400 border-b border-slate-800 pb-1 flex justify-between">
                              <span>Score Breakdown</span>
                              <span>Mode: {item.match_type}</span>
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                              <div>Keyword Score: <strong className="text-white">{((item.keyword_score || 0) * 100).toFixed(0)}%</strong></div>
                              <div>Similarity Score: <strong className="text-white">{((item.similarity_score || 0) * 100).toFixed(0)}%</strong></div>
                              <div>Hybrid Score: <strong className="text-indigo-300">{((item.hybrid_score || 0) * 100).toFixed(0)}%</strong></div>
                              <div>Priority: <strong className="text-emerald-400">{item.ranking_priority ?? 0}</strong></div>
                            </div>
                            {item.matched_fields && item.matched_fields.length > 0 && (
                              <div className="text-[11px] text-slate-400 pt-1">
                                Matched Fields: <span className="text-slate-200">{item.matched_fields.join(', ')}</span>
                              </div>
                            )}
                          </div>
                        )}

                        {item.commerce_description && (
                          <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed">
                            {item.commerce_description}
                          </p>
                        )}

                        {/* Attribute Badges */}
                        {item.attributes && item.attributes.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            {item.attributes.slice(0, 4).map((attr) => (
                              <span
                                key={attr.attribute_name}
                                className="bg-slate-950 border border-slate-800 text-slate-300 text-[11px] px-2.5 py-1 rounded-md flex items-center gap-1.5"
                              >
                                <span className="text-slate-400">{attr.display_name}:</span>
                                <strong className="text-white">{attr.raw_value}</strong>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

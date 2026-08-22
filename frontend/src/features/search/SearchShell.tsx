import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search,
  Loader2,
  Sparkles,
  Filter,
  ChevronRight
} from 'lucide-react';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';
import { apiUrl } from '../../lib/api';

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
  attributes: DynamicAttributeFacet[];
}

interface FacetSearchResponse {
  query: string;
  facets: FacetPayload;
}

export const SearchShell: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const initialQuery = searchParams.get('q') || '';
  const initialMode = searchParams.get('mode') || 'hybrid';

  const [query, setQuery] = useState<string>(initialQuery);
  const [searchMode, setSearchMode] = useState<string>(initialMode);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedBrands, setSelectedBrands] = useState<string[]>([]);
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);

  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [facets, setFacets] = useState<FacetPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const executeSearch = async () => {
    if (!query.trim()) {
      setSearchResults(null);
      setFacets(null);
      return;
    }
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.append('q', query.trim());
    params.append('mode', searchMode);
    if (selectedCategories.length > 0) params.append('category', selectedCategories.join(','));
    if (selectedBrands.length > 0) params.append('brand', selectedBrands.join(','));
    if (selectedStatuses.length > 0) params.append('status', selectedStatuses.join(','));

    try {
      const [searchRes, facetRes] = await Promise.all([
        fetch(apiUrl(`/api/v1/search?${params.toString()}`)),
        fetch(apiUrl(`/api/v1/search/facets?${params.toString()}`)),
      ]);

      if (!searchRes.ok) throw new Error(`Search failed: HTTP ${searchRes.status}`);
      const searchData: SearchResponse = await searchRes.json();
      setSearchResults(searchData);

      if (facetRes.ok) {
        const facetData: FacetSearchResponse = await facetRes.json();
        setFacets(facetData.facets);
      }
    } catch (err: any) {
      console.error('Search error:', err);
      setError(err?.message || 'Failed to perform search query');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (query.trim()) {
      executeSearch();
    }
  }, [searchMode, selectedCategories, selectedBrands, selectedStatuses]);

  const toggleCategory = (cat: string) => {
    setSelectedCategories(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
  };

  const toggleBrand = (b: string) => {
    setSelectedBrands(prev => prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]);
  };

  const toggleStatus = (s: string) => {
    setSelectedStatuses(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  };

  return (
    <div className="space-y-8 text-foreground rounded-none">
      {/* Header */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
          <Search className="w-3.5 h-3.5" />
          Hybrid Semantic Vector & Lexical Engine
        </div>
        <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
          Hybrid Vector & Lexical Search
        </h1>
        <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
          Dual-engine intelligence combining semantic vector embeddings in Qdrant with exact SKU lexical match boosting in PostgreSQL.
        </p>
      </div>

      {/* Main Search Command Bar */}
      <div className="p-5 border border-border bg-card space-y-4 rounded-none">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            executeSearch();
          }}
          className="flex items-center gap-3"
        >
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-muted-foreground absolute left-4 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by SKU, Model, specifications, or natural language query..."
              className="w-full pl-11 pr-4 py-3 bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground transition rounded-none font-light"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="h-11 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 text-[#9B8F77]" />}
            <span>Search</span>
          </button>
        </form>

        {/* Search Mode Pills & Intent indicator */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">Mode:</span>
            {[
              { id: 'hybrid', label: 'Hybrid (Fusion)' },
              { id: 'semantic', label: 'Semantic (Vector)' },
              { id: 'keyword', label: 'Keyword (Lexical)' },
            ].map((mode) => (
              <button
                key={mode.id}
                type="button"
                onClick={() => setSearchMode(mode.id)}
                className={`px-3 py-1 text-[10px] uppercase tracking-widest font-medium transition rounded-none border ${
                  searchMode === mode.id
                    ? 'bg-foreground text-background border-foreground'
                    : 'bg-background text-muted-foreground hover:text-foreground border-border hover:bg-card'
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          {searchResults?.query_intent && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Intent:</span>
              <span className="font-mono text-[10px] text-[#9B8F77] px-2 py-0.5 border border-border bg-background">
                {searchResults.query_intent}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Results Grid & Facet Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Facet Filters Sidebar */}
        <div className="space-y-6">
          <div className="p-5 border border-border bg-card space-y-5 rounded-none">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2">
                <Filter className="w-3.5 h-3.5" />
                <span>Filters & Facets</span>
              </h3>
              {(selectedCategories.length > 0 || selectedBrands.length > 0 || selectedStatuses.length > 0) && (
                <button
                  onClick={() => {
                    setSelectedCategories([]);
                    setSelectedBrands([]);
                    setSelectedStatuses([]);
                  }}
                  className="text-[9px] uppercase tracking-widest text-[#9B8F77] hover:text-foreground font-semibold"
                >
                  Reset
                </button>
              )}
            </div>

            {/* Categories Facet */}
            {facets?.categories && facets.categories.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] uppercase tracking-widest font-medium text-foreground">Category</div>
                <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
                  {facets.categories.map((cat) => (
                    <label
                      key={cat.value}
                      className="flex items-center justify-between text-xs text-muted-foreground hover:text-foreground cursor-pointer py-1 font-light"
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedCategories.includes(cat.value)}
                          onChange={() => toggleCategory(cat.value)}
                          className="rounded-none border-border bg-background text-foreground focus:ring-0"
                        />
                        <span className="truncate">{cat.value}</span>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground">({cat.count})</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Brands Facet */}
            {facets?.brands && facets.brands.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-border">
                <div className="text-[10px] uppercase tracking-widest font-medium text-foreground">Brand</div>
                <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
                  {facets.brands.map((b) => (
                    <label
                      key={b.value}
                      className="flex items-center justify-between text-xs text-muted-foreground hover:text-foreground cursor-pointer py-1 font-light"
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedBrands.includes(b.value)}
                          onChange={() => toggleBrand(b.value)}
                          className="rounded-none border-border bg-background text-foreground focus:ring-0"
                        />
                        <span className="truncate">{b.value}</span>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground">({b.count})</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Statuses Facet */}
            {facets?.statuses && facets.statuses.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-border">
                <div className="text-[10px] uppercase tracking-widest font-medium text-foreground">Status</div>
                <div className="space-y-1">
                  {facets.statuses.map((s) => (
                    <label
                      key={s.value}
                      className="flex items-center justify-between text-xs text-muted-foreground hover:text-foreground cursor-pointer py-1 font-light"
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={selectedStatuses.includes(s.value)}
                          onChange={() => toggleStatus(s.value)}
                          className="rounded-none border-border bg-background text-foreground focus:ring-0"
                        />
                        <span className="capitalize">{s.value}</span>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground">({s.count})</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Results Stream Column */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground uppercase tracking-wider font-light">
            <span>Found <strong className="text-foreground font-mono font-medium">{searchResults?.total ?? 0}</strong> products</span>
            {searchResults?.degraded_mode && (
              <span className="px-2 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-500 text-[9px] font-mono">
                Degraded: {searchResults.degraded_mode}
              </span>
            )}
          </div>

          {error && (
            <div className="p-4 border border-destructive/40 bg-destructive/10 text-xs text-destructive rounded-none font-mono">
              {error}
            </div>
          )}

          {loading ? (
            <div className="space-y-4 animate-pulse">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-40 border border-border bg-card rounded-none"></div>
              ))}
            </div>
          ) : !searchResults ? (
            <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
              <Search className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
              <h3 className="font-serif text-xl font-normal text-foreground">Explore Product Intelligence</h3>
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-light max-w-md mx-auto">
                Type a product SKU, brand name, technical attribute, or natural language query to search across the catalog.
              </p>
            </div>
          ) : searchResults.results.length === 0 ? (
            <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
              <Search className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
              <h3 className="font-serif text-xl font-normal text-foreground">No Results Found</h3>
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
                Try broadening your query keywords or clearing active filters.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {searchResults?.results.map((res) => (
                <div
                  key={res.product_id}
                  onClick={() => navigate(`/catalog?product_id=${res.product_id}`)}
                  className="p-6 border border-border bg-card space-y-4 hover:border-muted-foreground cursor-pointer transition group rounded-none"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-[#9B8F77] px-2 py-0.5 border border-border bg-background">
                          {res.manufacturer || 'Industrial'}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">SKU: {res.sku}</span>
                        {res.match_type && (
                          <span className="text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 border border-border bg-accent text-foreground">
                            {res.match_type}
                          </span>
                        )}
                      </div>
                      <h3 className="font-serif text-xl font-normal text-foreground group-hover:text-[#9B8F77] transition">
                        {res.product_name}
                      </h3>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <ConfidenceBadge confidence={res.quality_score} />
                      <StatusBadge status={res.status} size="sm" />
                    </div>
                  </div>

                  {res.commerce_description && (
                    <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed font-light">
                      {res.commerce_description}
                    </p>
                  )}

                  {/* Attributes Pills */}
                  {res.attributes && res.attributes.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {res.attributes.slice(0, 5).map((attr, i) => (
                        <span
                          key={i}
                          className="text-[10px] px-2 py-0.5 border border-border bg-background text-muted-foreground font-mono"
                        >
                          <strong className="text-foreground font-sans font-medium">{attr.display_name || attr.attribute_name}:</strong> {attr.raw_value}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="pt-2 flex items-center justify-between border-t border-border text-xs text-muted-foreground font-light">
                    <div className="flex items-center gap-3 font-mono text-[10px]">
                      {res.hybrid_score != null && (
                        <span>Hybrid: <strong className="text-emerald-500">{(res.hybrid_score * 100).toFixed(1)}%</strong></span>
                      )}
                      {res.similarity_score != null && (
                        <span>Vector: <strong className="text-[#9B8F77]">{(res.similarity_score * 100).toFixed(1)}%</strong></span>
                      )}
                    </div>
                    <span className="text-foreground group-hover:translate-x-1 transition-transform inline-flex items-center gap-1 text-[10px] uppercase tracking-widest font-medium">
                      <span>Inspect Specs</span>
                      <ChevronRight className="w-3.5 h-3.5 text-[#9B8F77]" />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

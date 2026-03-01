(function(){"use strict";/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */var et;const _e=globalThis,xe=_e.ShadowRoot&&(_e.ShadyCSS===void 0||_e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,$e=Symbol(),De=new WeakMap;let Pe=class{constructor(t,i,s){if(this._$cssResult$=!0,s!==$e)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=i}get styleSheet(){let t=this.o;const i=this.t;if(xe&&t===void 0){const s=i!==void 0&&i.length===1;s&&(t=De.get(i)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&De.set(i,t))}return t}toString(){return this.cssText}};const rt=e=>new Pe(typeof e=="string"?e:e+"",void 0,$e),O=(e,...t)=>{const i=e.length===1?e[0]:t.reduce((s,o,a)=>s+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+e[a+1],e[0]);return new Pe(i,e,$e)},lt=(e,t)=>{if(xe)e.adoptedStyleSheets=t.map(i=>i instanceof CSSStyleSheet?i:i.styleSheet);else for(const i of t){const s=document.createElement("style"),o=_e.litNonce;o!==void 0&&s.setAttribute("nonce",o),s.textContent=i.cssText,e.appendChild(s)}},Re=xe?e=>e:e=>e instanceof CSSStyleSheet?(t=>{let i="";for(const s of t.cssRules)i+=s.cssText;return rt(i)})(e):e;/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const{is:ct,defineProperty:dt,getOwnPropertyDescriptor:ht,getOwnPropertyNames:pt,getOwnPropertySymbols:ut,getPrototypeOf:mt}=Object,G=globalThis,Ie=G.trustedTypes,gt=Ie?Ie.emptyScript:"",Se=G.reactiveElementPolyfillSupport,le=(e,t)=>e,ve={toAttribute(e,t){switch(t){case Boolean:e=e?gt:null;break;case Object:case Array:e=e==null?e:JSON.stringify(e)}return e},fromAttribute(e,t){let i=e;switch(t){case Boolean:i=e!==null;break;case Number:i=e===null?null:Number(e);break;case Object:case Array:try{i=JSON.parse(e)}catch{i=null}}return i}},ke=(e,t)=>!ct(e,t),He={attribute:!0,type:String,converter:ve,reflect:!1,useDefault:!1,hasChanged:ke};Symbol.metadata??(Symbol.metadata=Symbol("metadata")),G.litPropertyMetadata??(G.litPropertyMetadata=new WeakMap);let ne=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??(this.l=[])).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,i=He){if(i.state&&(i.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((i=Object.create(i)).wrapped=!0),this.elementProperties.set(t,i),!i.noAccessor){const s=Symbol(),o=this.getPropertyDescriptor(t,s,i);o!==void 0&&dt(this.prototype,t,o)}}static getPropertyDescriptor(t,i,s){const{get:o,set:a}=ht(this.prototype,t)??{get(){return this[i]},set(r){this[i]=r}};return{get:o,set(r){const p=o==null?void 0:o.call(this);a==null||a.call(this,r),this.requestUpdate(t,p,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??He}static _$Ei(){if(this.hasOwnProperty(le("elementProperties")))return;const t=mt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(le("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(le("properties"))){const i=this.properties,s=[...pt(i),...ut(i)];for(const o of s)this.createProperty(o,i[o])}const t=this[Symbol.metadata];if(t!==null){const i=litPropertyMetadata.get(t);if(i!==void 0)for(const[s,o]of i)this.elementProperties.set(s,o)}this._$Eh=new Map;for(const[i,s]of this.elementProperties){const o=this._$Eu(i,s);o!==void 0&&this._$Eh.set(o,i)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const i=[];if(Array.isArray(t)){const s=new Set(t.flat(1/0).reverse());for(const o of s)i.unshift(Re(o))}else t!==void 0&&i.push(Re(t));return i}static _$Eu(t,i){const s=i.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){var t;this._$ES=new Promise(i=>this.enableUpdating=i),this._$AL=new Map,this._$E_(),this.requestUpdate(),(t=this.constructor.l)==null||t.forEach(i=>i(this))}addController(t){var i;(this._$EO??(this._$EO=new Set)).add(t),this.renderRoot!==void 0&&this.isConnected&&((i=t.hostConnected)==null||i.call(t))}removeController(t){var i;(i=this._$EO)==null||i.delete(t)}_$E_(){const t=new Map,i=this.constructor.elementProperties;for(const s of i.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return lt(t,this.constructor.elementStyles),t}connectedCallback(){var t;this.renderRoot??(this.renderRoot=this.createRenderRoot()),this.enableUpdating(!0),(t=this._$EO)==null||t.forEach(i=>{var s;return(s=i.hostConnected)==null?void 0:s.call(i)})}enableUpdating(t){}disconnectedCallback(){var t;(t=this._$EO)==null||t.forEach(i=>{var s;return(s=i.hostDisconnected)==null?void 0:s.call(i)})}attributeChangedCallback(t,i,s){this._$AK(t,s)}_$ET(t,i){var a;const s=this.constructor.elementProperties.get(t),o=this.constructor._$Eu(t,s);if(o!==void 0&&s.reflect===!0){const r=(((a=s.converter)==null?void 0:a.toAttribute)!==void 0?s.converter:ve).toAttribute(i,s.type);this._$Em=t,r==null?this.removeAttribute(o):this.setAttribute(o,r),this._$Em=null}}_$AK(t,i){var a,r;const s=this.constructor,o=s._$Eh.get(t);if(o!==void 0&&this._$Em!==o){const p=s.getPropertyOptions(o),c=typeof p.converter=="function"?{fromAttribute:p.converter}:((a=p.converter)==null?void 0:a.fromAttribute)!==void 0?p.converter:ve;this._$Em=o;const d=c.fromAttribute(i,p.type);this[o]=d??((r=this._$Ej)==null?void 0:r.get(o))??d,this._$Em=null}}requestUpdate(t,i,s,o=!1,a){var r;if(t!==void 0){const p=this.constructor;if(o===!1&&(a=this[t]),s??(s=p.getPropertyOptions(t)),!((s.hasChanged??ke)(a,i)||s.useDefault&&s.reflect&&a===((r=this._$Ej)==null?void 0:r.get(t))&&!this.hasAttribute(p._$Eu(t,s))))return;this.C(t,i,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,i,{useDefault:s,reflect:o,wrapped:a},r){s&&!(this._$Ej??(this._$Ej=new Map)).has(t)&&(this._$Ej.set(t,r??i??this[t]),a!==!0||r!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(i=void 0),this._$AL.set(t,i)),o===!0&&this._$Em!==t&&(this._$Eq??(this._$Eq=new Set)).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(i){Promise.reject(i)}const t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){var s;if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??(this.renderRoot=this.createRenderRoot()),this._$Ep){for(const[a,r]of this._$Ep)this[a]=r;this._$Ep=void 0}const o=this.constructor.elementProperties;if(o.size>0)for(const[a,r]of o){const{wrapped:p}=r,c=this[a];p!==!0||this._$AL.has(a)||c===void 0||this.C(a,void 0,r,c)}}let t=!1;const i=this._$AL;try{t=this.shouldUpdate(i),t?(this.willUpdate(i),(s=this._$EO)==null||s.forEach(o=>{var a;return(a=o.hostUpdate)==null?void 0:a.call(o)}),this.update(i)):this._$EM()}catch(o){throw t=!1,this._$EM(),o}t&&this._$AE(i)}willUpdate(t){}_$AE(t){var i;(i=this._$EO)==null||i.forEach(s=>{var o;return(o=s.hostUpdated)==null?void 0:o.call(s)}),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&(this._$Eq=this._$Eq.forEach(i=>this._$ET(i,this[i]))),this._$EM()}updated(t){}firstUpdated(t){}};ne.elementStyles=[],ne.shadowRootOptions={mode:"open"},ne[le("elementProperties")]=new Map,ne[le("finalized")]=new Map,Se==null||Se({ReactiveElement:ne}),(G.reactiveElementVersions??(G.reactiveElementVersions=[])).push("2.1.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const ce=globalThis,Oe=e=>e,fe=ce.trustedTypes,Le=fe?fe.createPolicy("lit-html",{createHTML:e=>e}):void 0,Ne="$lit$",q=`lit$${Math.random().toFixed(9).slice(2)}$`,We="?"+q,_t=`<${We}>`,X=document,de=()=>X.createComment(""),he=e=>e===null||typeof e!="object"&&typeof e!="function",Ce=Array.isArray,vt=e=>Ce(e)||typeof(e==null?void 0:e[Symbol.iterator])=="function",Te=`[ 	
\f\r]`,pe=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Fe=/-->/g,Ue=/>/g,ee=RegExp(`>|${Te}(?:([^\\s"'>=/]+)(${Te}*=${Te}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ve=/'/g,je=/"/g,Be=/^(?:script|style|textarea|title)$/i,ft=e=>(t,...i)=>({_$litType$:e,strings:t,values:i}),l=ft(1),te=Symbol.for("lit-noChange"),h=Symbol.for("lit-nothing"),Ke=new WeakMap,ie=X.createTreeWalker(X,129);function Ze(e,t){if(!Ce(e)||!e.hasOwnProperty("raw"))throw Error("invalid template strings array");return Le!==void 0?Le.createHTML(t):t}const yt=(e,t)=>{const i=e.length-1,s=[];let o,a=t===2?"<svg>":t===3?"<math>":"",r=pe;for(let p=0;p<i;p++){const c=e[p];let d,g,m=-1,v=0;for(;v<c.length&&(r.lastIndex=v,g=r.exec(c),g!==null);)v=r.lastIndex,r===pe?g[1]==="!--"?r=Fe:g[1]!==void 0?r=Ue:g[2]!==void 0?(Be.test(g[2])&&(o=RegExp("</"+g[2],"g")),r=ee):g[3]!==void 0&&(r=ee):r===ee?g[0]===">"?(r=o??pe,m=-1):g[1]===void 0?m=-2:(m=r.lastIndex-g[2].length,d=g[1],r=g[3]===void 0?ee:g[3]==='"'?je:Ve):r===je||r===Ve?r=ee:r===Fe||r===Ue?r=pe:(r=ee,o=void 0);const y=r===ee&&e[p+1].startsWith("/>")?" ":"";a+=r===pe?c+_t:m>=0?(s.push(d),c.slice(0,m)+Ne+c.slice(m)+q+y):c+q+(m===-2?p:y)}return[Ze(e,a+(e[i]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]};class ue{constructor({strings:t,_$litType$:i},s){let o;this.parts=[];let a=0,r=0;const p=t.length-1,c=this.parts,[d,g]=yt(t,i);if(this.el=ue.createElement(d,s),ie.currentNode=this.el.content,i===2||i===3){const m=this.el.content.firstChild;m.replaceWith(...m.childNodes)}for(;(o=ie.nextNode())!==null&&c.length<p;){if(o.nodeType===1){if(o.hasAttributes())for(const m of o.getAttributeNames())if(m.endsWith(Ne)){const v=g[r++],y=o.getAttribute(m).split(q),E=/([.?@])?(.*)/.exec(v);c.push({type:1,index:a,name:E[2],strings:y,ctor:E[1]==="."?wt:E[1]==="?"?xt:E[1]==="@"?$t:ye}),o.removeAttribute(m)}else m.startsWith(q)&&(c.push({type:6,index:a}),o.removeAttribute(m));if(Be.test(o.tagName)){const m=o.textContent.split(q),v=m.length-1;if(v>0){o.textContent=fe?fe.emptyScript:"";for(let y=0;y<v;y++)o.append(m[y],de()),ie.nextNode(),c.push({type:2,index:++a});o.append(m[v],de())}}}else if(o.nodeType===8)if(o.data===We)c.push({type:2,index:a});else{let m=-1;for(;(m=o.data.indexOf(q,m+1))!==-1;)c.push({type:7,index:a}),m+=q.length-1}a++}}static createElement(t,i){const s=X.createElement("template");return s.innerHTML=t,s}}function ae(e,t,i=e,s){var r,p;if(t===te)return t;let o=s!==void 0?(r=i._$Co)==null?void 0:r[s]:i._$Cl;const a=he(t)?void 0:t._$litDirective$;return(o==null?void 0:o.constructor)!==a&&((p=o==null?void 0:o._$AO)==null||p.call(o,!1),a===void 0?o=void 0:(o=new a(e),o._$AT(e,i,s)),s!==void 0?(i._$Co??(i._$Co=[]))[s]=o:i._$Cl=o),o!==void 0&&(t=ae(e,o._$AS(e,t.values),o,s)),t}class bt{constructor(t,i){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=i}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:i},parts:s}=this._$AD,o=((t==null?void 0:t.creationScope)??X).importNode(i,!0);ie.currentNode=o;let a=ie.nextNode(),r=0,p=0,c=s[0];for(;c!==void 0;){if(r===c.index){let d;c.type===2?d=new me(a,a.nextSibling,this,t):c.type===1?d=new c.ctor(a,c.name,c.strings,this,t):c.type===6&&(d=new St(a,this,t)),this._$AV.push(d),c=s[++p]}r!==(c==null?void 0:c.index)&&(a=ie.nextNode(),r++)}return ie.currentNode=X,o}p(t){let i=0;for(const s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,i),i+=s.strings.length-2):s._$AI(t[i])),i++}}class me{get _$AU(){var t;return((t=this._$AM)==null?void 0:t._$AU)??this._$Cv}constructor(t,i,s,o){this.type=2,this._$AH=h,this._$AN=void 0,this._$AA=t,this._$AB=i,this._$AM=s,this.options=o,this._$Cv=(o==null?void 0:o.isConnected)??!0}get parentNode(){let t=this._$AA.parentNode;const i=this._$AM;return i!==void 0&&(t==null?void 0:t.nodeType)===11&&(t=i.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,i=this){t=ae(this,t,i),he(t)?t===h||t==null||t===""?(this._$AH!==h&&this._$AR(),this._$AH=h):t!==this._$AH&&t!==te&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):vt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==h&&he(this._$AH)?this._$AA.nextSibling.data=t:this.T(X.createTextNode(t)),this._$AH=t}$(t){var a;const{values:i,_$litType$:s}=t,o=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=ue.createElement(Ze(s.h,s.h[0]),this.options)),s);if(((a=this._$AH)==null?void 0:a._$AD)===o)this._$AH.p(i);else{const r=new bt(o,this),p=r.u(this.options);r.p(i),this.T(p),this._$AH=r}}_$AC(t){let i=Ke.get(t.strings);return i===void 0&&Ke.set(t.strings,i=new ue(t)),i}k(t){Ce(this._$AH)||(this._$AH=[],this._$AR());const i=this._$AH;let s,o=0;for(const a of t)o===i.length?i.push(s=new me(this.O(de()),this.O(de()),this,this.options)):s=i[o],s._$AI(a),o++;o<i.length&&(this._$AR(s&&s._$AB.nextSibling,o),i.length=o)}_$AR(t=this._$AA.nextSibling,i){var s;for((s=this._$AP)==null?void 0:s.call(this,!1,!0,i);t!==this._$AB;){const o=Oe(t).nextSibling;Oe(t).remove(),t=o}}setConnected(t){var i;this._$AM===void 0&&(this._$Cv=t,(i=this._$AP)==null||i.call(this,t))}}class ye{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,i,s,o,a){this.type=1,this._$AH=h,this._$AN=void 0,this.element=t,this.name=i,this._$AM=o,this.options=a,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=h}_$AI(t,i=this,s,o){const a=this.strings;let r=!1;if(a===void 0)t=ae(this,t,i,0),r=!he(t)||t!==this._$AH&&t!==te,r&&(this._$AH=t);else{const p=t;let c,d;for(t=a[0],c=0;c<a.length-1;c++)d=ae(this,p[s+c],i,c),d===te&&(d=this._$AH[c]),r||(r=!he(d)||d!==this._$AH[c]),d===h?t=h:t!==h&&(t+=(d??"")+a[c+1]),this._$AH[c]=d}r&&!o&&this.j(t)}j(t){t===h?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class wt extends ye{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===h?void 0:t}}class xt extends ye{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==h)}}class $t extends ye{constructor(t,i,s,o,a){super(t,i,s,o,a),this.type=5}_$AI(t,i=this){if((t=ae(this,t,i,0)??h)===te)return;const s=this._$AH,o=t===h&&s!==h||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,a=t!==h&&(s===h||o);o&&this.element.removeEventListener(this.name,this,s),a&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){var i;typeof this._$AH=="function"?this._$AH.call(((i=this.options)==null?void 0:i.host)??this.element,t):this._$AH.handleEvent(t)}}class St{constructor(t,i,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=i,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){ae(this,t)}}const Ee=ce.litHtmlPolyfillSupport;Ee==null||Ee(ue,me),(ce.litHtmlVersions??(ce.litHtmlVersions=[])).push("3.3.2");const kt=(e,t,i)=>{const s=(i==null?void 0:i.renderBefore)??t;let o=s._$litPart$;if(o===void 0){const a=(i==null?void 0:i.renderBefore)??null;s._$litPart$=o=new me(t.insertBefore(de(),a),a,void 0,i??{})}return o._$AI(e),o};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const se=globalThis;let I=class extends ne{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){var i;const t=super.createRenderRoot();return(i=this.renderOptions).renderBefore??(i.renderBefore=t.firstChild),t}update(t){const i=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=kt(i,this.renderRoot,this.renderOptions)}connectedCallback(){var t;super.connectedCallback(),(t=this._$Do)==null||t.setConnected(!0)}disconnectedCallback(){var t;super.disconnectedCallback(),(t=this._$Do)==null||t.setConnected(!1)}render(){return te}};I._$litElement$=!0,I.finalized=!0,(et=se.litElementHydrateSupport)==null||et.call(se,{LitElement:I});const Ae=se.litElementPolyfillSupport;Ae==null||Ae({LitElement:I}),(se.litElementVersions??(se.litElementVersions=[])).push("4.2.2");/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const U=e=>(t,i)=>{i!==void 0?i.addInitializer(()=>{customElements.define(e,t)}):customElements.define(e,t)};/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const Ct={attribute:!0,type:String,converter:ve,reflect:!1,hasChanged:ke},Tt=(e=Ct,t,i)=>{const{kind:s,metadata:o}=i;let a=globalThis.litPropertyMetadata.get(o);if(a===void 0&&globalThis.litPropertyMetadata.set(o,a=new Map),s==="setter"&&((e=Object.create(e)).wrapped=!0),a.set(i.name,e),s==="accessor"){const{name:r}=i;return{set(p){const c=t.get.call(this);t.set.call(this,p),this.requestUpdate(r,c,e,!0,p)},init(p){return p!==void 0&&this.C(r,void 0,e,p),p}}}if(s==="setter"){const{name:r}=i;return function(p){const c=this[r];t.call(this,p),this.requestUpdate(r,c,e,!0,p)}}throw Error("Unsupported decorator location: "+s)};function _(e){return(t,i)=>typeof i=="object"?Tt(e,t,i):((s,o,a)=>{const r=o.hasOwnProperty(a);return o.constructor.createProperty(a,s),r?Object.getOwnPropertyDescriptor(o,a):void 0})(e,t,i)}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function u(e){return _({...e,state:!0,attribute:!1})}const be={en:{"panel.title":"RoomMind","panel.subtitle":"Climate management","panel.tab.rooms":"Rooms","panel.tab.settings":"Settings","panel.loading":"Loading...","panel.no_areas":"No areas configured in Home Assistant.","panel.no_areas_hint":"Add areas in HA settings to get started.","panel.stat.rooms":"Rooms","panel.stat.heating":"Heating","panel.stat.cooling":"Cooling","panel.hide_room":"Hide","panel.unhide":"Show","panel.hidden_rooms":"Hidden rooms","room.back":"Back to rooms","room.section.climate_mode":"Climate Mode","room.section.schedule":"Schedule & Temperatures","room.section.devices":"Devices","room.delete":"Delete room","room.deleting":"Deleting...","room.saving":"Saving...","room.saved":"Saved","room.error_saving":"Error saving","room.confirm_delete":'Remove RoomMind configuration for "{name}"?',"room.error_save_fallback":"Failed to save configuration","room.error_delete_fallback":"Failed to delete configuration","room.alias.placeholder":"Custom display name","room.alias.clear":"Reset to area name","override.label":"Temporary Override","override.comfort":"Comfort","override.eco":"Eco","override.custom":"Custom","override.target":"Target:","override.activate_for":"Activate for:","override.error_set":"Failed to set override","override.error_clear":"Failed to clear override","hero.target":"Target","hero.override":"Override","hero.remaining":"{time} remaining","hero.humidity":"{value}% humidity","hero.trv_setpoint":"Thermostat set to {value}{unit}","hero.waiting":"Waiting for sensor data...","hero.not_configured":"Not configured yet","card.target":"Target","card.waiting":"Waiting for data...","card.humidity":"{value}% humidity","card.thermostat":"Thermostat","card.thermostats":"Thermostats","card.ac":"AC","card.acs":"ACs","card.climate_device":"climate device","card.climate_devices":"climate devices","card.temp_sensor":"temp sensor","card.temp_sensors":"temp sensors","card.no_climate":"No climate devices","card.tap_configure":"Tap to configure","card.mpc_active":"MPC active","card.mpc_learning":"MPC learning","mode.auto":"Auto","mode.auto_desc":"Heats & cools automatically based on target temperature","mode.heat_only":"Heat Only","mode.heat_only_desc":"Only uses thermostats, ACs stay off","mode.cool_only":"Cool Only","mode.cool_only_desc":"Only uses ACs, thermostats stay off","mode.heating":"Heating","mode.cooling":"Cooling","mode.idle":"Standby","schedule.add_schedule":"Add schedule","schedule.selector_label":"Schedule selector entity","schedule.selector_value_boolean":"Current: {value}","schedule.selector_value_number":"Current value: {value}","schedule.selector_warning":"Multiple schedules but no selector set. Only the first will be used.","schedule.state_active":"Active","schedule.state_inactive":"Inactive","schedule.state_unreachable":"Unreachable","schedule.no_schedules":"No schedules configured","schedule.done":"Done","schedule.view_comfort":"Comfort: {temp}{unit}","schedule.view_eco":"Eco: {temp}{unit}","schedule.view_selector":"Active schedule selected by: {name}","schedule.view_selector_prefix":"Active schedule selected by:","schedule.help_header":"How do schedules work?","schedule.help_temps_title":"How is the target temperature determined?","schedule.help_temps":"The target temperature follows this priority chain:","schedule.help_temps_1":"<strong>Manual override</strong> – A temporary boost/eco/custom override always takes highest priority.","schedule.help_temps_2":"<strong>Block temperature</strong> – If the active schedule block has a <code>temperature</code> value in its data, that value is used.","schedule.help_temps_3":'<strong>Comfort temperature</strong> – If the schedule is "on" but the block has no temperature, the comfort fallback temperature below is used.',"schedule.help_temps_4":'<strong>Eco temperature</strong> – When the schedule is "off" (outside all time blocks), the eco temperature is used.',"schedule.help_block_title":"Setting temperature per time block","schedule.help_block":"You can set a specific temperature for each time block by adding a <code>temperature</code> value in the schedule's YAML configuration:","schedule.help_block_note":"If a block has no <code>temperature</code> data, the comfort fallback temperature is used instead.","schedule.help_multi_title":"Multiple schedules","schedule.help_multi":"You can add multiple schedules and switch between them using a <strong>selector entity</strong>. This can be an <code>input_boolean</code> (toggles between schedule 1 and 2) or an <code>input_number</code> (selects by number). Without a selector entity, only the first schedule is used.","schedule.comfort_label":"Fallback comfort temperature","schedule.eco_label":"Eco temperature","schedule.comfort_hint":'Used when schedule is "on" but no temperature is set in the block',"schedule.from_schedule":"{temp}{unit} from schedule","schedule.fallback":"{temp}{unit} (fallback)","schedule.eco_detail":"{temp}{unit} (eco)","devices.climate_entities":"Climate entities","devices.temp_sensors":"Temperature sensors","devices.humidity_sensors":"Humidity sensors","devices.no_climate":"No climate entities found in this area.","devices.no_temp_sensors":"No temperature sensors found in this area.","devices.no_humidity_sensors":"No humidity sensors found in this area.","devices.window_sensors":"Window / door sensors","devices.no_window_sensors":"No window/door sensors found in this area.","devices.window_open_delay":"Delay before pausing","devices.window_close_delay":"Delay before resuming","devices.add_entity":"Add entity","devices.done":"Done","devices.other_area":"Other area","devices.type_thermostat":"Thermostat","devices.type_ac":"AC","hero.window_open":"Window open – paused","card.window_open":"Window open","settings.general_title":"General","settings.climate_control_active":"Climate control active","settings.climate_control_hint":"When disabled, RoomMind continues to monitor all sensors and train the model, but will not send any commands to your heating or cooling devices.","settings.learning_title":"Model Training","settings.learning_hint":"When paused, RoomMind stops collecting new measurement data and training the thermal model. Existing model data is preserved.","settings.learning_exceptions":"Exceptions","settings.learning_room_paused":"room paused","settings.learning_rooms_paused":"rooms paused","settings.sensors_title":"Sensors & Data Sources","settings.control_title":"Control","settings.outdoor_sensor":"Outdoor Temperature","settings.outdoor_sensor_label":"Outdoor temperature sensor","settings.outdoor_current":"Currently {temp}{unit} outside","settings.outdoor_waiting":"Waiting for sensor data...","settings.outdoor_humidity_sensor":"Outdoor Humidity","settings.outdoor_humidity_label":"Outdoor humidity sensor","settings.outdoor_humidity_current":"Currently {value}% outside","settings.smart_control":"Smart Climate Control","settings.smart_control_hint":"Configure outdoor temperature limits for heating and cooling.","settings.outdoor_cooling_min":"Minimum outdoor temp for cooling","settings.outdoor_cooling_min_hint":"AC stays off when outdoor temperature is below this value","settings.outdoor_heating_max":"Maximum outdoor temp for heating","settings.outdoor_heating_max_hint":"Heating stays off when outdoor temperature exceeds this value","settings.saving":"Saving...","settings.saved":"Saved","settings.error":"Error saving","devices.using_builtin_sensor":"Using thermostat's built-in sensor","settings.climate_intelligence":"Climate Intelligence","settings.control_mode":"Control Mode","settings.control_mode_simple":"Simple (Bang-Bang)","settings.control_mode_mpc":"Intelligent (MPC)","settings.control_mode_hint":"MPC learns your room's thermal behavior for optimal control","settings.comfort_weight":"Priority","settings.comfort_weight_comfort":"Comfort","settings.comfort_weight_efficiency":"Efficiency","settings.weather_entity":"Weather Forecast","settings.weather_entity_hint":"Optional: enables predictive outdoor temperature planning","settings.prediction_enabled":"Temperature prediction","settings.prediction_enabled_hint":"Show predicted temperature trend in analytics charts. Disable if you experience slow performance.","vacation.title":"Vacation Mode","vacation.hint":"Sets all rooms to a setback temperature until the end date.","vacation.active_label":"Vacation mode active","vacation.end_date":"End date & time","vacation.setback_temp":"Setback temperature","vacation.banner_title":"Vacation mode active","vacation.banner_detail":"{temp}{unit} until {date}","vacation.deactivate":"Deactivate","tabs.analytics":"Analytics","analytics.select_room":"Select Room","analytics.temperature":"Temperature","analytics.target":"Target","analytics.prediction":"Prediction","analytics.outdoor":"Outdoor","analytics.model_status":"Model Status","analytics.confidence":"Confidence","analytics.heating_rate":"Heating Strength","analytics.cooling_rate":"Cooling Strength","analytics.solar_gain":"Solar Gain","analytics.time_constant":"Time Constant","analytics.samples":"Samples","analytics.prediction_accuracy":"Prediction Accuracy","analytics.avg_deviation":"Avg. Deviation","analytics.data_sources":"Data Sources","analytics.data_points":"Data Points","analytics.control_mode":"Control Mode","analytics.control_mode_mpc":"MPC active","analytics.control_mode_bangbang":"MPC learning","analytics.last_model_update":"Last Model Update","analytics.accuracy_idle":"Accuracy (Idle)","analytics.accuracy_heating":"Accuracy (Heating)","analytics.info.accuracy_idle":"How precisely the model predicts temperature when neither heating nor cooling is active. A lower value means the model understands your room's natural heat loss well. This is the first value to improve because idle data is collected continuously.","analytics.info.accuracy_heating":"How precisely the model predicts temperature during active heating. This value stays high initially because the model needs real heating cycles to learn from. Once your heating has run a few times, this value will drop and MPC control becomes available.","analytics.info.confidence":"Overall model readiness for intelligent MPC control, combining two factors: data quantity (how many idle and active-mode samples have been collected) and prediction accuracy (how precise the temperature forecasts are). Confidence starts at 0% and rises as the model collects data and learns. Around 50% means enough idle data but still waiting for heating/cooling cycles. Above 80% means the model has enough data and accurate predictions — MPC control becomes available. 100% is the theoretical maximum when predictions are as accurate as physically possible.","analytics.info.time_constant":"How long it takes your room to naturally cool down halfway toward the outdoor temperature when heating is off. A longer time constant means better insulation — the room holds warmth longer. A short time constant means the room cools quickly. The model learns this by observing temperature drops during idle periods.","analytics.info.heating_rate":"How strongly your heating affects the room temperature. A higher value means your heating system warms the room faster relative to its thermal mass. The model learns this by observing how quickly the temperature rises during active heating, and uses it to predict how long heating needs to run.","analytics.info.cooling_rate":"How strongly your AC affects the room temperature. A higher value means the AC cools the room faster relative to its thermal mass. The model learns this by observing how quickly the temperature drops during active cooling, and uses it to predict how long the AC needs to run.","analytics.info.solar_gain":"The estimated effect of solar radiation through windows on room temperature. The model learns this by observing how the room warms during sunny periods when heating is off. Rooms with large south-facing windows will have higher values. The model uses this to reduce heating when solar gain is expected.","analytics.info.data_sources":"Number of measurement samples used for model training.","analytics.info.data_points":"Total number of observations the model has been trained on. More data points generally lead to better predictions. The model collects a new data point roughly every 3 minutes while RoomMind is running.","analytics.no_data":"No data yet — model is learning","analytics.loading":"Loading analytics...","settings.reset_title":"Reset Thermal Data","settings.reset_hint":"Clear learned thermal model data and history. The model will start learning from scratch.","settings.reset_all_label":"All rooms","settings.reset_all_hint":"Clear thermal data and history for all rooms at once.","settings.reset_all_btn":"Reset all","settings.reset_all_confirm":"Clear all learned thermal data and history for ALL rooms? All models will start learning from scratch.","settings.reset_room_label":"Individual room","settings.reset_room_hint":"Select a room to clear its thermal data and history.","settings.reset_room_confirm":"Clear all learned thermal data and history for this room? The model will start learning from scratch.","settings.reset_room_select":"Select room","settings.reset_btn":"Reset","settings.reset_no_rooms":"No configured rooms.","analytics.range_1d":"Today","analytics.range_2d":"2 days","analytics.range_7d":"Week","analytics.range_30d":"Month","analytics.export":"Measurements","analytics.heating_period":"Heating","analytics.cooling_period":"Cooling","analytics.window_open_period":"Window open","analytics.chart_info_title":"How to read this chart","analytics.exported":"Exported!","analytics.copy_diagnostics":"Model diagnostics","analytics.export_download":"Download file","analytics.export_clipboard":"Copy to clipboard","analytics.copied_to_clipboard":"Copied!","analytics.range_from":"From","analytics.range_to":"To","analytics.chart_info_body":`**Lines:** The solid orange line shows the measured room temperature. The green dashed line is the target temperature from your schedule. The blue dotted line is the model's temperature prediction.

**Shaded areas:** Red shading marks heating periods, blue marks cooling, and teal marks times when a window was open.

**Future forecast (right of the 'now' line):** The green dashed line shows the upcoming schedule targets for the next 3 hours. The blue dotted line shows the predicted temperature trend.

**Prediction modes:** When 'MPC active' is shown, the prediction uses the full MPC optimizer with intelligent pre-heating/pre-cooling. While the model is still learning, a simpler simulation is used.

**Limitations:** The prediction assumes current conditions stay constant (outdoor temperature, window state). The simulation accuracy depends on how well the thermal model has learned your room — early on, predictions may be less accurate. Once MPC activates, predictions become significantly more reliable.`,"presence.title":"Presence Detection","presence.hint":"Uses eco temperature when nobody is home.","presence.hint_detail":"When enabled, all rooms switch to eco temperature as soon as none of the configured persons are home. You can optionally restrict per room which persons are relevant.","presence.add_person":"Add person","presence.person_label":"Person","presence.banner_title":"Nobody home","presence.banner_detail":"All rooms set to eco temperature","room.section.presence":"Presence","presence.room_help_header":"How does per-room presence work?","presence.room_help_body":"Select which persons are relevant for this room. The room switches to eco temperature when none of the selected persons are home. Without selection, the global rule applies: eco when nobody is home.","presence.state_home":"Home","presence.state_away":"Away","presence.room_none_assigned":"Global rule — eco when nobody is home","card.presence_away":"Away","valve_protection.title":"Valve Protection","valve_protection.hint":"Periodically opens idle TRV valves briefly to prevent seizing or calcification.","valve_protection.interval_label":"Cycle interval","valve_protection.interval_suffix":"days","valve_protection.interval_hint":"How long a valve can be idle before being cycled (1–90 days)","mold.title":"Mold Risk Protection","mold.detection":"Mold Detection","mold.detection_desc":"Receive notifications when humidity indicates mold risk","mold.threshold":"Humidity threshold (%)","mold.threshold_hint":"Alert when room humidity stays above this value","mold.sustained":"Sustained duration (minutes)","mold.sustained_hint":"Alert only after risk persists for this long","mold.cooldown":"Notification cooldown (minutes)","mold.cooldown_hint":"Minimum time between repeated alerts per room","mold.target_person":"Person","mold.target_when_always":"Always","mold.target_when_home":"Only when home","mold.prevention":"Mold Prevention","mold.prevention_desc":"Automatically raise temperature to reduce mold risk","mold.intensity":"Intensity","mold.intensity_light":"Light (+{delta}{unit})","mold.intensity_medium":"Medium (+{delta}{unit})","mold.intensity_strong":"Strong (+{delta}{unit})","mold.intensity_hint":"Warmer air reduces surface humidity on cold walls. Light is usually sufficient for moderate risk, Strong can lower surface humidity by up to 8–10% — but uses noticeably more energy.","mold.prevention_notify":"Notify when prevention activates","mold.prevention_notify_hint":"Also send a notification when prevention activates (temperature raised)","mold.notifications_title":"Notifications","mold.notifications_enabled":"Enable notifications","mold.notifications_enabled_hint":"When disabled, no notifications are sent — neither to devices nor to the HA sidebar.","mold.notifications_desc":"Choose which devices receive mold risk alerts. Without targets, alerts appear in the HA sidebar.","mold.add_target_label":"Add notification device","mold.add_target_hint":"Type the entity ID if your device is not listed (e.g. notify.mobile_app_...). You can find it under Settings → Devices → your phone → Notify entity.","mold.target_unnamed":"Unnamed device","card.mold_warning":"Mold risk","card.mold_critical":"Mold danger!","card.mold_prevention":"Mold prevention +{delta}{unit}","room.mold_surface_rh":"Est. surface humidity: {value}%"},de:{"panel.title":"RoomMind","panel.subtitle":"Klimasteuerung","panel.tab.rooms":"Räume","panel.tab.settings":"Einstellungen","panel.loading":"Laden...","panel.no_areas":"Keine Bereiche in Home Assistant konfiguriert.","panel.no_areas_hint":"Bereiche in den HA-Einstellungen anlegen.","panel.stat.rooms":"Räume","panel.stat.heating":"Heizen","panel.stat.cooling":"Kühlen","panel.hide_room":"Ausblenden","panel.unhide":"Einblenden","panel.hidden_rooms":"Ausgeblendete Räume","room.back":"Zurück zu den Räumen","room.section.climate_mode":"Klimamodus","room.section.schedule":"Zeitplan & Temperaturen","room.section.devices":"Geräte","room.delete":"Raum löschen","room.deleting":"Wird gelöscht...","room.saving":"Speichern...","room.saved":"Gespeichert","room.error_saving":"Fehler beim Speichern","room.confirm_delete":'RoomMind-Konfiguration für "{name}" entfernen?',"room.error_save_fallback":"Konfiguration konnte nicht gespeichert werden","room.error_delete_fallback":"Konfiguration konnte nicht gelöscht werden","room.alias.placeholder":"Eigener Anzeigename","room.alias.clear":"Auf Bereichsname zurücksetzen","override.label":"Temporärer Override","override.comfort":"Komfort","override.eco":"Eco","override.custom":"Individuell","override.target":"Ziel:","override.activate_for":"Aktivieren für:","override.error_set":"Override konnte nicht gesetzt werden","override.error_clear":"Override konnte nicht aufgehoben werden","hero.target":"Ziel","hero.override":"Override","hero.remaining":"noch {time}","hero.humidity":"{value}% Luftfeuchtigkeit","hero.trv_setpoint":"Thermostat auf {value}{unit}","hero.waiting":"Warte auf Sensordaten...","hero.not_configured":"Noch nicht konfiguriert","card.target":"Ziel","card.waiting":"Warte auf Daten...","card.humidity":"{value}% Luftfeuchtigkeit","card.thermostat":"Thermostat","card.thermostats":"Thermostate","card.ac":"Klimaanlage","card.acs":"Klimaanlagen","card.climate_device":"Klimagerät","card.climate_devices":"Klimageräte","card.temp_sensor":"Temperatursensor","card.temp_sensors":"Temperatursensoren","card.no_climate":"Keine Klimageräte","card.tap_configure":"Tippen zum Konfigurieren","card.mpc_active":"MPC aktiv","card.mpc_learning":"MPC lernt","mode.auto":"Automatisch","mode.auto_desc":"Heizt und kühlt automatisch basierend auf der Zieltemperatur","mode.heat_only":"Nur Heizen","mode.heat_only_desc":"Nutzt nur Thermostate, Klimaanlagen bleiben aus","mode.cool_only":"Nur Kühlen","mode.cool_only_desc":"Nutzt nur Klimaanlagen, Thermostate bleiben aus","mode.heating":"Heizen","mode.cooling":"Kühlen","mode.idle":"Standby","schedule.add_schedule":"Zeitplan hinzufügen","schedule.selector_label":"Zeitplan-Auswahl","schedule.selector_value_boolean":"Aktuell: {value}","schedule.selector_value_number":"Aktueller Wert: {value}","schedule.selector_warning":"Mehrere Zeitpläne, aber keine Auswahl-Entity gesetzt. Nur der erste wird verwendet.","schedule.state_active":"Aktiv","schedule.state_inactive":"Inaktiv","schedule.state_unreachable":"Nicht erreichbar","schedule.no_schedules":"Keine Zeitpläne konfiguriert","schedule.done":"Fertig","schedule.view_comfort":"Komfort: {temp}{unit}","schedule.view_eco":"Eco: {temp}{unit}","schedule.view_selector":"Aktiver Zeitplan gewählt durch: {name}","schedule.view_selector_prefix":"Aktiver Zeitplan gewählt durch:","schedule.help_header":"Wie funktionieren Zeitpläne?","schedule.help_temps_title":"Wie wird die Zieltemperatur bestimmt?","schedule.help_temps":"Die Zieltemperatur folgt dieser Prioritätskette:","schedule.help_temps_1":"<strong>Manueller Override</strong> – Ein temporärer Komfort-/Eco-/Individueller Override hat immer die höchste Priorität.","schedule.help_temps_2":"<strong>Block-Temperatur</strong> – Wenn der aktive Zeitblock einen <code>temperature</code>-Wert in seinen Daten hat, wird dieser verwendet.","schedule.help_temps_3":'<strong>Komforttemperatur</strong> – Wenn der Zeitplan "an" ist, aber der Block keine Temperatur hat, wird die Komfort-Fallback-Temperatur verwendet.',"schedule.help_temps_4":'<strong>Eco-Temperatur</strong> – Wenn der Zeitplan "aus" ist (außerhalb aller Zeitblöcke), wird die Eco-Temperatur verwendet.',"schedule.help_block_title":"Temperatur pro Zeitblock setzen","schedule.help_block":"Du kannst für jeden Zeitblock eine eigene Temperatur setzen, indem du einen <code>temperature</code>-Wert in der YAML-Konfiguration des Zeitplans angibst:","schedule.help_block_note":"Wenn ein Block keinen <code>temperature</code>-Wert hat, wird stattdessen die Komfort-Fallback-Temperatur verwendet.","schedule.help_multi_title":"Mehrere Zeitpläne","schedule.help_multi":"Du kannst mehrere Zeitpläne hinzufügen und mit einer <strong>Auswahl-Entity</strong> zwischen ihnen wechseln. Das kann ein <code>input_boolean</code> (wechselt zwischen Zeitplan 1 und 2) oder ein <code>input_number</code> (wählt nach Nummer) sein. Ohne Auswahl-Entity wird nur der erste Zeitplan verwendet.","schedule.comfort_label":"Komfort-Fallback-Temperatur","schedule.eco_label":"Eco-Temperatur","schedule.comfort_hint":'Wird verwendet wenn der Zeitplan "an" ist, aber keine Temperatur im Block gesetzt ist',"schedule.from_schedule":"{temp}{unit} vom Zeitplan","schedule.fallback":"{temp}{unit} (Fallback)","schedule.eco_detail":"{temp}{unit} (Eco)","devices.climate_entities":"Klimageräte","devices.temp_sensors":"Temperatursensoren","devices.humidity_sensors":"Feuchtigkeitssensoren","devices.no_climate":"Keine Klimageräte in diesem Bereich gefunden.","devices.no_temp_sensors":"Keine Temperatursensoren in diesem Bereich gefunden.","devices.no_humidity_sensors":"Keine Feuchtigkeitssensoren in diesem Bereich gefunden.","devices.window_sensors":"Fenster- / Türsensoren","devices.no_window_sensors":"Keine Fenster-/Türsensoren in diesem Bereich gefunden.","devices.window_open_delay":"Verzögerung vor Pause","devices.window_close_delay":"Verzögerung vor Wiederaufnahme","devices.add_entity":"Entität hinzufügen","devices.done":"Fertig","devices.other_area":"Anderer Bereich","devices.type_thermostat":"Thermostat","devices.type_ac":"Klimaanlage","hero.window_open":"Fenster offen – pausiert","card.window_open":"Fenster offen","settings.general_title":"Allgemein","settings.climate_control_active":"Klimasteuerung aktiv","settings.climate_control_hint":"Wenn deaktiviert, überwacht RoomMind weiterhin alle Sensoren und trainiert das Modell, steuert aber keine Heizungen oder Klimaanlagen mehr an.","settings.learning_title":"Modell-Training","settings.learning_hint":"Wenn pausiert, sammelt RoomMind keine neuen Messdaten und trainiert das thermische Modell nicht weiter. Bestehende Modelldaten bleiben erhalten.","settings.learning_exceptions":"Ausnahmen","settings.learning_room_paused":"Raum pausiert","settings.learning_rooms_paused":"Räume pausiert","settings.sensors_title":"Sensoren & Datenquellen","settings.control_title":"Steuerung","settings.outdoor_sensor":"Außentemperatur","settings.outdoor_sensor_label":"Außentemperatursensor","settings.outdoor_current":"Aktuell {temp}{unit} draußen","settings.outdoor_waiting":"Warte auf Sensordaten...","settings.outdoor_humidity_sensor":"Außenluftfeuchtigkeit","settings.outdoor_humidity_label":"Außenluftfeuchtigkeitssensor","settings.outdoor_humidity_current":"Aktuell {value}% draußen","settings.smart_control":"Intelligente Klimasteuerung","settings.smart_control_hint":"Außentemperaturgrenzen für Heiz- und Kühlentscheidungen konfigurieren.","settings.outdoor_cooling_min":"Mindest-Außentemperatur für Kühlung","settings.outdoor_cooling_min_hint":"Klimaanlage bleibt aus wenn Außentemperatur unter diesem Wert","settings.outdoor_heating_max":"Maximal-Außentemperatur für Heizung","settings.outdoor_heating_max_hint":"Heizung bleibt aus wenn Außentemperatur über diesem Wert","settings.saving":"Speichern...","settings.saved":"Gespeichert","settings.error":"Fehler beim Speichern","devices.using_builtin_sensor":"Nutzt den eingebauten Thermostat-Sensor","settings.climate_intelligence":"Klimaintelligenz","settings.control_mode":"Steuerungsmodus","settings.control_mode_simple":"Einfach (Ein/Aus)","settings.control_mode_mpc":"Intelligent (MPC)","settings.control_mode_hint":"MPC lernt das thermische Verhalten deiner Räume für optimale Steuerung","settings.comfort_weight":"Priorität","settings.comfort_weight_comfort":"Komfort","settings.comfort_weight_efficiency":"Effizienz","settings.weather_entity":"Wettervorhersage","settings.weather_entity_hint":"Optional: ermöglicht vorausschauende Außentemperaturplanung","settings.prediction_enabled":"Temperaturvorhersage","settings.prediction_enabled_hint":"Zeigt den vorhergesagten Temperaturverlauf im Analyse-Diagramm. Bei langsamer Performance deaktivieren.","vacation.title":"Urlaubsmodus","vacation.hint":"Setzt alle Räume auf eine Absenktemperatur bis zum Enddatum.","vacation.active_label":"Urlaubsmodus aktiv","vacation.end_date":"Enddatum & Uhrzeit","vacation.setback_temp":"Absenktemperatur","vacation.banner_title":"Urlaubsmodus aktiv","vacation.banner_detail":"{temp}{unit} bis {date}","vacation.deactivate":"Deaktivieren","tabs.analytics":"Analyse","analytics.select_room":"Raum auswählen","analytics.temperature":"Temperatur","analytics.target":"Ziel","analytics.prediction":"Vorhersage","analytics.outdoor":"Außen","analytics.model_status":"Modellstatus","analytics.confidence":"Konfidenz","analytics.heating_rate":"Heizstärke","analytics.cooling_rate":"Kühlstärke","analytics.solar_gain":"Solargewinn","analytics.time_constant":"Zeitkonstante","analytics.samples":"Datenpunkte","analytics.prediction_accuracy":"Vorhersagegenauigkeit","analytics.avg_deviation":"Durchschn. Abweichung","analytics.data_sources":"Datenquellen","analytics.data_points":"Datenpunkte","analytics.control_mode":"Steuerungsmodus","analytics.control_mode_mpc":"MPC aktiv","analytics.control_mode_bangbang":"MPC wird trainiert","analytics.last_model_update":"Letztes Modell-Update","analytics.accuracy_idle":"Genauigkeit (Leerlauf)","analytics.accuracy_heating":"Genauigkeit (Heizen)","analytics.info.accuracy_idle":"Wie genau das Modell die Temperatur vorhersagt, wenn weder geheizt noch gekühlt wird. Ein niedrigerer Wert bedeutet, dass das Modell den natürlichen Wärmeverlust deines Raums gut versteht. Dieser Wert verbessert sich als erstes, da Leerlauf-Daten kontinuierlich gesammelt werden.","analytics.info.accuracy_heating":"Wie genau das Modell die Temperatur während des aktiven Heizens vorhersagt. Dieser Wert bleibt anfangs hoch, da das Modell echte Heizzyklen zum Lernen braucht. Sobald deine Heizung ein paar Mal gelaufen ist, sinkt dieser Wert und die intelligente MPC-Steuerung wird verfügbar.","analytics.info.confidence":"Gesamte Modellreife für die intelligente MPC-Steuerung, basierend auf zwei Faktoren: Datenmenge (wie viele Leerlauf- und Aktiv-Messwerte gesammelt wurden) und Vorhersagegenauigkeit (wie präzise die Temperaturprognosen sind). Die Konfidenz startet bei 0% und steigt mit zunehmenden Daten. Etwa 50% bedeutet: genug Leerlaufdaten, aber noch zu wenig Heiz-/Kühlzyklen. Über 80% bedeutet: genug Daten und genaue Vorhersagen — MPC-Steuerung wird verfügbar. 100% ist das theoretische Maximum, wenn die Vorhersagen so genau wie physikalisch möglich sind.","analytics.info.time_constant":"Wie lange es dauert, bis sich die Raumtemperatur bei ausgeschalteter Heizung halbwegs der Außentemperatur annähert. Eine längere Zeitkonstante bedeutet bessere Dämmung — der Raum hält die Wärme länger. Eine kurze Zeitkonstante bedeutet schnelles Auskühlen. Das Modell lernt diesen Wert, indem es Temperaturabfälle im Leerlauf beobachtet.","analytics.info.heating_rate":"Wie stark deine Heizung die Raumtemperatur beeinflusst. Ein höherer Wert bedeutet, dass dein Heizsystem den Raum schneller erwärmt relativ zur thermischen Masse. Das Modell lernt dies durch Beobachtung der Temperaturanstiege beim Heizen und nutzt es um vorherzusagen, wie lange geheizt werden muss.","analytics.info.cooling_rate":"Wie stark deine Klimaanlage die Raumtemperatur beeinflusst. Ein höherer Wert bedeutet schnellere Kühlung relativ zur thermischen Masse. Das Modell lernt dies durch Beobachtung der Temperaturabfälle bei aktiver Kühlung und nutzt es um vorherzusagen, wie lange gekühlt werden muss.","analytics.info.solar_gain":"Der geschätzte Effekt der Sonneneinstrahlung durch Fenster auf die Raumtemperatur. Wird gelernt, indem beobachtet wird, wie sich der Raum bei Sonnenschein erwärmt, wenn nicht geheizt wird. Räume mit großen Südfenstern haben höhere Werte. Das Modell nutzt dies um die Heizung zu reduzieren, wenn Solargewinn erwartet wird.","analytics.info.data_sources":"Anzahl der Messwerte, die für das Modelltraining verwendet werden.","analytics.info.data_points":"Gesamtzahl der Beobachtungen, mit denen das Modell trainiert wurde. Mehr Datenpunkte führen in der Regel zu besseren Vorhersagen. Das Modell sammelt etwa alle 3 Minuten einen neuen Datenpunkt während RoomMind läuft.","analytics.no_data":"Noch keine Daten — Modell lernt","analytics.loading":"Analyse wird geladen...","settings.reset_title":"Thermische Daten zurücksetzen","settings.reset_hint":"Gelernte thermische Modelldaten und Verlauf löschen. Das Modell beginnt von vorne zu lernen.","settings.reset_all_label":"Alle Räume","settings.reset_all_hint":"Thermische Daten und Verlauf für alle Räume auf einmal löschen.","settings.reset_all_btn":"Alle zurücksetzen","settings.reset_all_confirm":"Alle gelernten thermischen Daten und Verlauf für ALLE Räume löschen? Alle Modelle beginnen von vorne zu lernen.","settings.reset_room_label":"Einzelner Raum","settings.reset_room_hint":"Wähle einen Raum, um dessen thermische Daten und Verlauf zu löschen.","settings.reset_room_confirm":"Alle gelernten thermischen Daten und Verlauf für diesen Raum löschen? Das Modell beginnt von vorne zu lernen.","settings.reset_room_select":"Raum auswählen","settings.reset_btn":"Zurücksetzen","settings.reset_no_rooms":"Keine konfigurierten Räume.","analytics.range_1d":"Heute","analytics.range_2d":"2 Tage","analytics.range_7d":"Woche","analytics.range_30d":"Monat","analytics.export":"Messdaten","analytics.heating_period":"Heizen","analytics.cooling_period":"Kühlung","analytics.window_open_period":"Fenster offen","analytics.chart_info_title":"So liest du dieses Diagramm","analytics.exported":"Exportiert!","analytics.copy_diagnostics":"Modell-Diagnose","analytics.export_download":"Datei herunterladen","analytics.export_clipboard":"In Zwischenablage kopieren","analytics.copied_to_clipboard":"Kopiert!","analytics.range_from":"Von","analytics.range_to":"Bis","analytics.chart_info_body":`**Linien:** Die durchgezogene orangene Linie zeigt die gemessene Raumtemperatur. Die grüne gestrichelte Linie ist die Zieltemperatur aus deinem Zeitplan. Die blaue gepunktete Linie ist die Temperaturvorhersage des Modells.

**Schattierte Bereiche:** Rote Schattierung markiert Heizperioden, blaue Kühlung und türkise Bereiche zeigen an, wenn ein Fenster offen war.

**Zukunftsprognose (rechts der 'Jetzt'-Linie):** Die grüne gestrichelte Linie zeigt die kommenden Zieltemperaturen für die nächsten 3 Stunden. Die blaue gepunktete Linie zeigt den vorhergesagten Temperaturverlauf.

**Vorhersage-Modus:** Wenn 'MPC aktiv' angezeigt wird, nutzt die Vorhersage den vollständigen MPC-Optimizer mit intelligentem Vorheizen/-kühlen. Solange das Modell noch lernt, wird eine einfachere Simulation verwendet.

**Einschränkungen:** Die Vorhersage nimmt an, dass aktuelle Bedingungen konstant bleiben (Außentemperatur, Fensterstatus). Die Genauigkeit hängt davon ab, wie gut das Modell deinen Raum bereits gelernt hat — anfangs können die Vorhersagen ungenau sein. Sobald MPC aktiviert wird, werden die Vorhersagen deutlich zuverlässiger.`,"presence.title":"Anwesenheitserkennung","presence.hint":"Eco-Temperatur wenn niemand zu Hause ist.","presence.hint_detail":"Wenn aktiviert, werden alle Räume auf Eco-Temperatur gesetzt, sobald keine der konfigurierten Personen zu Hause ist. Pro Raum kann optional eingeschränkt werden, welche Personen relevant sind.","presence.add_person":"Person hinzufügen","presence.person_label":"Person","presence.banner_title":"Niemand zu Hause","presence.banner_detail":"Alle Räume auf Eco-Temperatur","room.section.presence":"Anwesenheit","presence.room_help_header":"Wie funktioniert die Raum-Anwesenheit?","presence.room_help_body":"Wähle aus, welche Personen für diesen Raum relevant sind. Der Raum schaltet auf Eco-Temperatur, wenn keine der ausgewählten Personen zu Hause ist. Ohne Auswahl greift die globale Regel: Eco wenn niemand zu Hause ist.","presence.state_home":"Zu Hause","presence.state_away":"Abwesend","presence.room_none_assigned":"Globale Regel — Eco wenn niemand zu Hause ist","card.presence_away":"Abwesend","valve_protection.title":"Ventilschutz","valve_protection.hint":"Bewegt inaktive TRV-Ventile regelmäßig kurz, um Festsitzen oder Verkalkung zu verhindern.","valve_protection.interval_label":"Zyklusintervall","valve_protection.interval_suffix":"Tage","valve_protection.interval_hint":"Wie lange ein Ventil inaktiv sein darf, bevor es bewegt wird (1–90 Tage)","mold.title":"Schimmelschutz","mold.detection":"Schimmelerkennung","mold.detection_desc":"Benachrichtigung bei Schimmelgefahr durch hohe Luftfeuchtigkeit","mold.threshold":"Feuchtigkeitsschwelle (%)","mold.threshold_hint":"Warnung wenn die Raumluftfeuchte diesen Wert dauerhaft überschreitet","mold.sustained":"Mindestdauer (Minuten)","mold.sustained_hint":"Warnung erst nach anhaltender Überschreitung","mold.cooldown":"Benachrichtigungspause (Minuten)","mold.cooldown_hint":"Mindestabstand zwischen wiederholten Warnungen pro Raum","mold.target_person":"Person","mold.target_when_always":"Immer","mold.target_when_home":"Nur wenn zuhause","mold.prevention":"Schimmelprävention","mold.prevention_desc":"Temperatur automatisch erhöhen um Schimmelrisiko zu senken","mold.intensity":"Intensität","mold.intensity_light":"Leicht (+{delta}{unit})","mold.intensity_medium":"Mittel (+{delta}{unit})","mold.intensity_strong":"Stark (+{delta}{unit})","mold.intensity_hint":"Wärmere Raumluft senkt die Oberflächenfeuchte an kalten Wänden. Leicht reicht meist bei moderatem Risiko, Stark kann die Oberflächenfeuchte um bis zu 8–10 % senken — verbraucht aber deutlich mehr Energie.","mold.prevention_notify":"Bei Aktivierung benachrichtigen","mold.prevention_notify_hint":"Auch benachrichtigen wenn die Prävention aktiviert wird (Temperaturerhöhung)","mold.notifications_title":"Benachrichtigungen","mold.notifications_enabled":"Benachrichtigungen aktivieren","mold.notifications_enabled_hint":"Wenn deaktiviert, werden keine Benachrichtigungen gesendet — weder an Geräte noch an die HA-Seitenleiste.","mold.notifications_desc":"Wähle die Geräte, die bei Schimmelgefahr benachrichtigt werden. Ohne Ziele erscheint eine Meldung in der HA-Seitenleiste.","mold.add_target_label":"Benachrichtigungsgerät hinzufügen","mold.add_target_hint":"Tippe die Entity-ID ein, falls dein Gerät nicht angezeigt wird (z.B. notify.mobile_app_...). Du findest sie unter Einstellungen → Geräte → dein Telefon → Notify-Entität.","mold.target_unnamed":"Unbenanntes Gerät","card.mold_warning":"Schimmelrisiko","card.mold_critical":"Schimmelgefahr!","card.mold_prevention":"Schimmelschutz +{delta}{unit}","room.mold_surface_rh":"Geschätzte Oberflächenfeuchte: {value}%"}};function n(e,t,i){let o=(be[t]??be[t.split("-")[0]]??be.en)[e]??be.en[e]??e;if(i)for(const[a,r]of Object.entries(i))o=o.replaceAll(`{${a}}`,String(r));return o}function Et(e,t){if(e.area_id)return e.area_id;if(e.device_id&&t){const i=t[e.device_id];if(i!=null&&i.area_id)return i.area_id}return null}function Ge(e,t,i){return t?Object.values(t).filter(s=>Et(s,i)===e):[]}function qe(e){switch(e){case"heating":return"mode-heating";case"cooling":return"mode-cooling";case"idle":return"mode-idle";default:return"mode-other"}}const At={heating:"mode.heating",cooling:"mode.cooling",idle:"mode.idle"};function Qe(e,t){return n(At[e],t)}const Ye=O`
  .mode-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 14px;
    border-radius: 16px;
  }

  .mode-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .mode-heating {
    color: var(--warning-color, #ff9800);
    background: rgba(255, 152, 0, 0.12);
  }
  .mode-heating .mode-dot {
    background: var(--warning-color, #ff9800);
  }

  .mode-cooling {
    color: #2196f3;
    background: rgba(33, 150, 243, 0.12);
  }
  .mode-cooling .mode-dot {
    background: #2196f3;
  }

  .mode-idle {
    color: var(--secondary-text-color, #757575);
    background: rgba(0, 0, 0, 0.05);
  }
  .mode-idle .mode-dot {
    background: var(--disabled-text-color, #bdbdbd);
  }

  .mode-other {
    color: var(--secondary-text-color);
    background: rgba(0, 0, 0, 0.05);
  }
  .mode-other .mode-dot {
    background: var(--secondary-text-color);
  }
`,Je="M11.83,9L15,12.16C15,12.11 15,12.05 15,12A3,3 0 0,0 12,9C11.94,9 11.89,9 11.83,9M7.53,9.8L9.08,11.35C9.03,11.56 9,11.77 9,12A3,3 0 0,0 12,15C12.22,15 12.44,14.97 12.65,14.92L14.2,16.47C13.53,16.8 12.79,17 12,17A5,5 0 0,1 7,12C7,11.21 7.2,10.47 7.53,9.8M2,4.27L4.28,6.55L4.73,7C3.08,8.3 1.78,10 1,12C2.73,16.39 7,19.5 12,19.5C13.55,19.5 15.03,19.2 16.38,18.66L16.81,19.08L19.73,22L21,20.73L3.27,3M12,7A5,5 0 0,1 17,12C17,12.64 16.87,13.26 16.64,13.82L19.57,16.75C21.07,15.5 22.27,13.86 23,12C21.27,7.61 17,4.5 12,4.5C10.6,4.5 9.26,4.75 8,5.2L10.17,7.35C10.74,7.13 11.35,7 12,7Z";function C(e){return e?"°F":"°C"}var Mt=Object.defineProperty,zt=Object.getOwnPropertyDescriptor,Q=(e,t,i,s)=>{for(var o=s>1?void 0:s?zt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Mt(t,i,o),o};let V=class extends I{constructor(){super(...arguments),this.config=null,this.climateEntityCount=0,this.tempSensorCount=0,this.controlMode="bangbang",this.useImperial=!1}render(){var r,p,c,d,g,m;const e=this.climateEntityCount>0,t=(((p=(r=this.config)==null?void 0:r.thermostats)==null?void 0:p.length)??0)>0||(((d=(c=this.config)==null?void 0:c.acs)==null?void 0:d.length)??0)>0,i=this.config!==null&&t,s=(g=this.config)==null?void 0:g.live,o=s==null?void 0:s.mode,a=i?o==="heating"?"accent-heating":o==="cooling"?"accent-cooling":"accent-idle":"accent-unconfigured";return l`
      <ha-card
        @click=${this._onCardClick}
      >
        <div class="accent ${a}"></div>
        <ha-icon-button
          class="hide-btn"
          .path=${Je}
          @click=${this._onHideClick}
        ></ha-icon-button>
        <div class="card-inner">
          <div class="card-header">
            <h3 class="area-name">${((m=this.config)==null?void 0:m.display_name)||this.area.name}</h3>
            ${i&&s?l`
                  <span class="mode-pill ${qe(s.mode)}">
                    <span class="mode-dot"></span>
                    ${Qe(s.mode,this.hass.language)}${s.heating_power>0&&s.heating_power<100?l` ${s.heating_power}%`:h}
                  </span>
                `:h}
          </div>

          ${i?this._renderConfigured():this._renderUnconfigured(e)}
        </div>
      </ha-card>
    `}_renderConfigured(){var i;const e=(i=this.config)==null?void 0:i.live;if(!e)return l`<div class="waiting">${n("card.waiting",this.hass.language)}</div>`;const t=this.controlMode==="mpc";return l`
      <div class="temp-section">
        ${e.current_temp!==null?l`
              <span class="current-temp">${e.current_temp.toFixed(1)}</span>
              <span class="temp-unit">${C(this.useImperial)}</span>
            `:l`<span class="no-temp">--</span>`}
        ${this._renderTargetInfo(e)}
      </div>
      <div class="card-footer">
        <span class="humidity-info">
          ${e.current_humidity!==null?n("card.humidity",this.hass.language,{value:e.current_humidity.toFixed(0)}):h}
        </span>
        <span class="badge-row">
          ${e.mold_risk_level&&e.mold_risk_level!=="ok"?l`<span class="mold-badge ${e.mold_risk_level}">
                <ha-icon icon="mdi:water-alert"></ha-icon>
                ${e.mold_risk_level==="critical"?n("card.mold_critical",this.hass.language):n("card.mold_warning",this.hass.language)}
              </span>`:h}
          ${e.mold_prevention_active?l`<span class="mold-badge prevention">
                <ha-icon icon="mdi:shield-check"></ha-icon>
                ${n("card.mold_prevention",this.hass.language,{delta:String(e.mold_prevention_delta),unit:C(this.useImperial)})}
              </span>`:h}
          ${t?l`<span class="mpc-badge ${e.mpc_active?"active":"learning"}">
                <ha-icon .icon=${e.mpc_active?"mdi:brain":"mdi:school-outline"}></ha-icon>
                ${e.mpc_active?n("card.mpc_active",this.hass.language):n("card.mpc_learning",this.hass.language)}
              </span>`:h}
        </span>
      </div>
    `}_renderTargetInfo(e){return e.target_temp===null?h:l`
      <span class="target-info">
        ${n("card.target",this.hass.language)} <span class="target-value">${e.target_temp.toFixed(1)}${C(this.useImperial)}</span>
        ${e.override_active?l`<ha-icon class="override-icon" icon="mdi:timer-outline"></ha-icon>`:h}
        ${e.window_open?l`<ha-icon class="window-icon" icon="mdi:window-open-variant"></ha-icon>`:h}
        ${e.presence_away?l`<ha-icon class="away-icon" icon="mdi:home-off-outline"></ha-icon>`:h}
      </span>
    `}_renderUnconfigured(e){const t=this.hass.language;if(!e)return l`<div class="device-summary empty">${n("card.no_climate",t)}</div>`;const i=this.climateEntityCount,s=this.tempSensorCount;return l`
      <div class="device-summary">
        ${i} ${n(i!==1?"card.climate_devices":"card.climate_device",t)}${s>0?` · ${s} ${n(s!==1?"card.temp_sensors":"card.temp_sensor",t)}`:""}
      </div>
      <div class="configure-prompt">
        <span class="configure-text">${n("card.tap_configure",t)}</span>
        <span class="configure-arrow">\u203A</span>
      </div>
    `}_onCardClick(){this.dispatchEvent(new CustomEvent("area-selected",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}_onHideClick(e){e.stopPropagation(),this.dispatchEvent(new CustomEvent("hide-room",{detail:{areaId:this.area.area_id},bubbles:!0,composed:!0}))}};V.styles=[Ye,O`
    :host {
      display: block;
    }

    ha-card {
      cursor: pointer;
      transition: box-shadow 0.2s ease, transform 0.15s ease;
      overflow: hidden;
      position: relative;
      height: 100%;
      box-sizing: border-box;
    }

    ha-card:hover {
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
      transform: translateY(-1px);
    }

    .hide-btn {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
      color: var(--secondary-text-color);
      opacity: 0;
      transition: opacity 0.2s ease;
      position: absolute;
      top: 8px;
      right: 8px;
    }

    ha-card:hover .hide-btn {
      opacity: 0.4;
    }

    .hide-btn:hover {
      opacity: 1 !important;
    }

    /* Colored left accent based on mode */
    .accent {
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
    }

    .accent-heating {
      background: var(--warning-color, #ff9800);
    }

    .accent-cooling {
      background: #2196f3;
    }

    .accent-idle {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .accent-unconfigured {
      background: transparent;
    }

    .card-inner {
      padding: 20px 20px 16px;
    }

    /* Header row: name + badge */
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .area-name {
      font-size: 15px;
      font-weight: 500;
      color: var(--primary-text-color);
      margin: 0;
      letter-spacing: 0.01em;
    }

    /* Card-specific mode-pill overrides (smaller than default) */
    .mode-pill {
      gap: 5px;
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 12px;
    }

    .mode-dot {
      width: 7px;
      height: 7px;
    }

    /* Temperature display */
    .temp-section {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin: 12px 0 0 0;
    }

    .current-temp {
      font-size: 36px;
      font-weight: 300;
      color: var(--primary-text-color);
      line-height: 1;
    }

    .temp-unit {
      font-size: 18px;
      font-weight: 300;
      color: var(--secondary-text-color);
    }

    .target-info {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-left: auto;
    }

    .target-value {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .override-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .window-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--warning-color, #ff9800);
    }

    .away-icon {
      --mdc-icon-size: 14px;
      vertical-align: middle;
      margin-left: 4px;
      color: var(--info-color, #2196f3);
    }

    /* Footer row: humidity + MPC status */
    .card-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 8px;
      min-height: 20px;
    }

    .humidity-info {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .mpc-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mpc-badge.active {
      color: var(--success-color, #4caf50);
      background: rgba(76, 175, 80, 0.12);
    }

    .mpc-badge.learning {
      color: var(--secondary-text-color);
      background: rgba(158, 158, 158, 0.1);
    }

    .mold-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 500;
      padding: 2px 8px 2px 6px;
      border-radius: 10px;
      --mdc-icon-size: 14px;
    }

    .mold-badge.warning {
      color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.12);
    }

    .mold-badge.critical {
      color: var(--error-color, #db4437);
      background: rgba(219, 68, 55, 0.12);
    }

    .mold-badge.prevention {
      color: var(--info-color, #2196f3);
      background: rgba(33, 150, 243, 0.12);
    }

    .badge-row {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .no-temp {
      font-size: 24px;
      font-weight: 300;
      color: var(--secondary-text-color);
      line-height: 1;
    }

    /* Device summary for unconfigured cards */
    .device-summary {
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 8px;
    }

    .device-summary.empty {
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
    }

    /* Configure prompt for unconfigured areas */
    .configure-prompt {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .configure-text {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .configure-arrow {
      font-size: 18px;
      color: var(--primary-color);
    }

    /* Waiting state */
    .waiting {
      font-size: 13px;
      color: var(--disabled-text-color, #9e9e9e);
      font-style: italic;
      margin-top: 8px;
    }
  `],Q([_({attribute:!1})],V.prototype,"area",2),Q([_({attribute:!1})],V.prototype,"config",2),Q([_({type:Number})],V.prototype,"climateEntityCount",2),Q([_({type:Number})],V.prototype,"tempSensorCount",2),Q([_({attribute:!1})],V.prototype,"hass",2),Q([_({type:String})],V.prototype,"controlMode",2),Q([_({type:Boolean})],V.prototype,"useImperial",2),V=Q([U("rs-area-card")],V);var Dt=Object.defineProperty,Pt=Object.getOwnPropertyDescriptor,B=(e,t,i,s)=>{for(var o=s>1?void 0:s?Pt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Dt(t,i,o),o};const Rt="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",It="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";let N=class extends I{constructor(){super(...arguments),this.config=null,this.overrideInfo=null,this.useImperial=!1,this._countdown="",this._editingName=!1,this._nameInput=""}disconnectedCallback(){super.disconnectedCallback(),this._clearCountdownTimer()}updated(e){(e.has("overrideInfo")||e.has("config"))&&this._updateCountdown()}_clearCountdownTimer(){this._countdownTimer&&(clearInterval(this._countdownTimer),this._countdownTimer=void 0)}_getOverrideUntil(){var e;return(e=this.overrideInfo)!=null&&e.active?this.overrideInfo.until:null}_updateCountdown(){if(this._clearCountdownTimer(),!this._getOverrideUntil()){this._countdown="";return}const t=()=>{const i=this._getOverrideUntil();if(!i){this._countdown="",this._clearCountdownTimer();return}const s=i-Date.now()/1e3;if(s<=0){this._countdown="",this._clearCountdownTimer();return}const o=Math.floor(s/3600),a=Math.floor(s%3600/60);this._countdown=o>0?`${o}h ${a}m`:`${a}m`};t(),this._countdownTimer=setInterval(t,3e4)}_getEffectiveOverride(){var e;return(e=this.overrideInfo)!=null&&e.active?this.overrideInfo:null}_renderTargetSection(e){var o;const t=((o=this.hass)==null?void 0:o.language)??"en",i=this._getEffectiveOverride(),s=C(this.useImperial);if(i){const a=i.type==="boost"?"mdi:fire":i.type==="eco"?"mdi:leaf":"mdi:thermometer",r=i.type==="boost"?n("override.comfort",t):i.type==="eco"?n("override.eco",t):n("override.custom",t),p=`override-${i.type}`,c=i.temp??e;return l`
        <div class="hero-target">
          <div class="hero-target-label ${p}">
            <ha-icon icon=${a}></ha-icon>
            ${r} ${n("hero.override",t)}
          </div>
          <div class="hero-target-value">
            ${c!==null?l`${c.toFixed(1)}${s}`:"--"}
          </div>
          ${this._countdown?l`<div class="hero-target-countdown">${n("hero.remaining",t,{time:this._countdown})}</div>`:h}
        </div>
      `}return e!==null?l`
        <div class="hero-target">
          <div class="hero-target-label">${n("hero.target",t)}</div>
          <div class="hero-target-value">${e.toFixed(1)}${s}</div>
        </div>
      `:h}_onEditName(){var e;this._nameInput=((e=this.config)==null?void 0:e.display_name)||"",this._editingName=!0,this.updateComplete.then(()=>{const t=this.renderRoot.querySelector(".name-input");t==null||t.focus(),t==null||t.select()})}_onNameInput(e){this._nameInput=e.target.value}_onNameKeydown(e){e.key==="Enter"?this._onNameDone():e.key==="Escape"&&(this._editingName=!1)}_onNameDone(){const e=this._nameInput.trim();this.dispatchEvent(new CustomEvent("display-name-changed",{detail:{value:e},bubbles:!0,composed:!0})),this._editingName=!1}_onNameClear(){this.dispatchEvent(new CustomEvent("display-name-changed",{detail:{value:""},bubbles:!0,composed:!0})),this._editingName=!1,this._nameInput=""}render(){var s,o,a,r,p,c,d,g,m,v,y,E,k;const e=(s=this.config)==null?void 0:s.live,t=e==null?void 0:e.mode;return l`
      <ha-card>
        <div class="hero-accent ${e?t==="heating"?"hero-accent-heating":t==="cooling"?"hero-accent-cooling":"hero-accent-idle":"hero-accent-none"}"></div>
        <div class="hero-header">
          ${this._editingName?l`
                <div class="name-edit-row">
                  <input
                    class="name-input"
                    type="text"
                    .value=${this._nameInput}
                    placeholder=${n("room.alias.placeholder",((o=this.hass)==null?void 0:o.language)??"en")}
                    @input=${this._onNameInput}
                    @keydown=${this._onNameKeydown}
                  />
                  <ha-icon-button
                    class="name-done-btn"
                    .path=${It}
                    @click=${this._onNameDone}
                  ></ha-icon-button>
                </div>
                ${(a=this.config)!=null&&a.display_name?l`<button class="name-clear-btn" @click=${this._onNameClear}>
                      ${n("room.alias.clear",((r=this.hass)==null?void 0:r.language)??"en")}
                    </button>`:h}
              `:l`
                <div class="name-row">
                  <h2 class="area-name">${((p=this.config)==null?void 0:p.display_name)||this.area.name}</h2>
                  <ha-icon-button
                    class="name-edit-btn"
                    .path=${Rt}
                    @click=${this._onEditName}
                  ></ha-icon-button>
                </div>
              `}
          ${e?l`
                <span class="mode-pill ${qe(e.mode)}">
                  <span class="mode-dot"></span>
                  ${Qe(e.mode,((c=this.hass)==null?void 0:c.language)??"en")}${e.heating_power>0&&e.heating_power<100?l` ${e.heating_power}%`:h}
                </span>
              `:h}
        </div>
        ${e?l`
              ${e.window_open?l`<div class="hero-window-open">
                    <ha-icon icon="mdi:window-open-variant"></ha-icon>
                    ${n("hero.window_open",((d=this.hass)==null?void 0:d.language)??"en")}
                  </div>`:h}
              <div class="hero-temps">
                ${e.current_temp!==null?l`
                      <span class="hero-current">${e.current_temp.toFixed(1)}</span>
                      <span class="hero-unit">${C(this.useImperial)}</span>
                    `:l`<span class="hero-current" style="opacity: 0.3">--</span>`}
                ${this._renderTargetSection(e.target_temp)}
              </div>
              ${e.current_humidity!==null?l`<div class="hero-metric">
                    <ha-icon icon="mdi:water-percent"></ha-icon>
                    ${n("hero.humidity",((g=this.hass)==null?void 0:g.language)??"en",{value:e.current_humidity.toFixed(0)})}
                  </div>`:h}
              ${e.trv_setpoint!=null?l`<div class="hero-metric">
                    <ha-icon icon="mdi:radiator"></ha-icon>
                    ${n("hero.trv_setpoint",((m=this.hass)==null?void 0:m.language)??"en",{value:e.trv_setpoint.toFixed(1),unit:C(this.useImperial)})}
                  </div>`:h}
              ${e.mold_surface_rh!=null?l`<div class="hero-metric ${e.mold_risk_level==="critical"?"critical":e.mold_risk_level==="warning"?"warning":""}">
                    <ha-icon icon="mdi:water-alert"></ha-icon>
                    ${n("room.mold_surface_rh",((v=this.hass)==null?void 0:v.language)??"en",{value:String(e.mold_surface_rh.toFixed(0))})}
                  </div>`:h}
              ${e.mold_prevention_active?l`<div class="hero-metric info">
                    <ha-icon icon="mdi:shield-check"></ha-icon>
                    ${n("card.mold_prevention",((y=this.hass)==null?void 0:y.language)??"en",{delta:String(e.mold_prevention_delta),unit:C(this.useImperial)})}
                  </div>`:h}
            `:this.config?l`<div class="hero-no-data">${n("hero.waiting",((E=this.hass)==null?void 0:E.language)??"en")}</div>`:l`<div class="hero-no-data">${n("hero.not_configured",((k=this.hass)==null?void 0:k.language)??"en")}</div>`}
      </ha-card>
    `}};N.styles=[Ye,O`
      :host {
        display: block;
      }

      ha-card {
        padding: 28px 24px;
        position: relative;
        overflow: hidden;
      }

      .hero-accent {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
      }

      .hero-accent-heating {
        background: linear-gradient(90deg, var(--warning-color, #ff9800), #ffb74d);
      }

      .hero-accent-cooling {
        background: linear-gradient(90deg, #2196f3, #64b5f6);
      }

      .hero-accent-idle {
        background: linear-gradient(
          90deg,
          var(--disabled-text-color, #bdbdbd),
          #e0e0e0
        );
      }

      .hero-accent-none {
        background: var(--divider-color, #e0e0e0);
      }

      .hero-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
      }

      .area-name {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        margin: 0;
      }

      .hero-temps {
        display: flex;
        align-items: baseline;
        gap: 8px;
      }

      .hero-current {
        font-size: 48px;
        font-weight: 300;
        color: var(--primary-text-color);
        line-height: 1;
      }

      .hero-unit {
        font-size: 24px;
        font-weight: 300;
        color: var(--secondary-text-color);
      }

      .hero-target {
        margin-left: auto;
        text-align: right;
      }

      .hero-target-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .hero-target-value {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
      }

      /* Override-aware target styling */
      .hero-target-label.override-boost {
        color: var(--warning-color, #ff9800);
      }

      .hero-target-label.override-eco {
        color: #4caf50;
      }

      .hero-target-label.override-custom {
        color: #2196f3;
      }

      .hero-target-label ha-icon {
        --mdc-icon-size: 12px;
        vertical-align: middle;
      }

      .hero-target-countdown {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 2px;
      }

      .hero-metric {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 14px;
        color: var(--secondary-text-color);
        margin-top: 6px;
      }

      .hero-metric ha-icon {
        --mdc-icon-size: 16px;
        flex-shrink: 0;
      }

      .hero-metric.warning {
        color: var(--warning-color, #ff9800);
      }

      .hero-metric.critical {
        color: var(--error-color, #db4437);
      }

      .hero-metric.info {
        color: var(--info-color, #2196f3);
      }

      .hero-no-data {
        font-size: 14px;
        color: var(--disabled-text-color, #9e9e9e);
        font-style: italic;
        padding: 8px 0;
      }

      .hero-window-open {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        margin-bottom: 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: var(--warning-color, #ff9800);
        background: rgba(255, 152, 0, 0.1);
      }

      .hero-window-open ha-icon {
        --mdc-icon-size: 18px;
      }

      .name-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-edit-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--secondary-text-color);
        opacity: 0;
        transition: opacity 0.15s;
      }

      .name-row:hover .name-edit-btn {
        opacity: 1;
      }

      @media (hover: none) {
        .name-edit-btn {
          opacity: 0.5;
        }
      }

      .name-edit-row {
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .name-input {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        background: transparent;
        border: none;
        border-bottom: 2px solid var(--primary-color);
        outline: none;
        padding: 0 0 2px;
        width: 100%;
        font-family: inherit;
      }

      .name-done-btn {
        --mdc-icon-button-size: 28px;
        --mdc-icon-size: 16px;
        color: var(--primary-color);
      }

      .name-clear-btn {
        background: none;
        border: none;
        color: var(--secondary-text-color);
        font-size: 12px;
        cursor: pointer;
        padding: 2px 0;
        text-decoration: underline;
      }
    `],B([_({attribute:!1})],N.prototype,"hass",2),B([_({attribute:!1})],N.prototype,"area",2),B([_({attribute:!1})],N.prototype,"config",2),B([_({attribute:!1})],N.prototype,"overrideInfo",2),B([_({type:Boolean})],N.prototype,"useImperial",2),B([u()],N.prototype,"_countdown",2),B([u()],N.prototype,"_editingName",2),B([u()],N.prototype,"_nameInput",2),N=B([U("rs-hero-status")],N);var Ht=Object.defineProperty,Ot=Object.getOwnPropertyDescriptor,Me=(e,t,i,s)=>{for(var o=s>1?void 0:s?Ot(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Ht(t,i,o),o};let ge=class extends I{constructor(){super(...arguments),this.climateMode="auto",this.language="en"}render(){const e=this.language;return l`
      <div class="mode-grid">
        ${[{value:"auto",labelKey:"mode.auto",icon:"mdi:autorenew"},{value:"heat_only",labelKey:"mode.heat_only",icon:"mdi:fire"},{value:"cool_only",labelKey:"mode.cool_only",icon:"mdi:snowflake"}].map(i=>l`
            <button
              class="mode-card"
              ?active=${this.climateMode===i.value}
              @click=${()=>this._onModeClick(i.value)}
            >
              <ha-icon class="mode-card-icon" icon=${i.icon}></ha-icon>
              <div class="mode-card-label">${n(i.labelKey,e)}</div>
            </button>
          `)}
      </div>
    `}_onModeClick(e){this.dispatchEvent(new CustomEvent("mode-changed",{detail:{mode:e},bubbles:!0,composed:!0}))}};ge.styles=O`
    :host {
      display: block;
    }

    .mode-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }

    .mode-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      padding: 14px 8px;
      border: 2px solid var(--divider-color, #e0e0e0);
      border-radius: 12px;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
      background: transparent;
      font-family: inherit;
      color: var(--primary-text-color);
      text-align: center;
    }

    .mode-card:hover {
      border-color: var(--primary-color, #03a9f4);
      box-shadow: 0 2px 8px rgba(3, 169, 244, 0.1);
    }

    .mode-card[active] {
      border-color: var(--primary-color, #03a9f4);
      background: rgba(3, 169, 244, 0.06);
      box-shadow: 0 2px 8px rgba(3, 169, 244, 0.12);
    }

    .mode-card-icon {
      --mdc-icon-size: 24px;
    }

    .mode-card[active] .mode-card-icon {
      color: var(--primary-color, #03a9f4);
    }

    .mode-card-label {
      font-weight: 500;
      font-size: 13px;
    }

    .mode-card[active] .mode-card-label {
      color: var(--primary-color, #03a9f4);
    }
  `,Me([_({type:String})],ge.prototype,"climateMode",2),Me([_({type:String})],ge.prototype,"language",2),ge=Me([U("rs-climate-mode-selector")],ge);/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */const Lt={CHILD:2},Nt=e=>(...t)=>({_$litDirective$:e,values:t});class Wt{constructor(t){}get _$AU(){return this._$AM._$AU}_$AT(t,i,s){this._$Ct=t,this._$AM=i,this._$Ci=s}_$AS(t,i){return this.update(t,i)}update(t,i){return this.render(...i)}}/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class ze extends Wt{constructor(t){if(super(t),this.it=h,t.type!==Lt.CHILD)throw Error(this.constructor.directiveName+"() can only be used in child bindings")}render(t){if(t===h||t==null)return this._t=void 0,this.it=t;if(t===te)return t;if(typeof t!="string")throw Error(this.constructor.directiveName+"() called with a non-string value");if(t===this.it)return this._t;this.it=t;const i=[t];return i.raw=i,this._t={_$litType$:this.constructor.resultType,strings:i,values:[]}}}ze.directiveName="unsafeHTML",ze.resultType=1;const oe=Nt(ze);function L(e,t){e.dispatchEvent(new CustomEvent("save-status",{detail:{status:t},bubbles:!0,composed:!0}))}function we(e,t){e.dispatchEvent(new CustomEvent("hass-more-info",{bubbles:!0,composed:!0,detail:{entityId:t}}))}var Ft=Object.defineProperty,Ut=Object.getOwnPropertyDescriptor,K=(e,t,i,s)=>{for(var o=s>1?void 0:s?Ut(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Ft(t,i,o),o};let W=class extends I{constructor(){super(...arguments),this.schedules=[],this.scheduleSelectorEntity="",this.activeScheduleIndex=0,this.comfortTemp=21,this.ecoTemp=17,this.editing=!1,this.useImperial=!1}render(){return this.editing?this._renderEditMode():this._renderViewMode()}_renderViewMode(){var i,s,o,a;const e=this.hass.language,t=this.schedules.length>=2;return l`
      ${this.schedules.length>0?l`
          <div class="schedule-list">
            ${this.schedules.map((r,p)=>{var m,v,y;const c=this._getScheduleState(p),d=(v=(m=this.hass)==null?void 0:m.states)==null?void 0:v[r.entity_id],g=((y=d==null?void 0:d.attributes)==null?void 0:y.friendly_name)||r.entity_id;return l`
                <div class="schedule-row ${c}">
                  ${t?l`<span class="schedule-number">${p+1}</span>`:h}
                  <span class="schedule-status-dot"></span>
                  <span class="schedule-name schedule-link" @click=${()=>we(this,r.entity_id)}>${g}</span>
                  <span class="schedule-status">${this._getStatusText(p,c)}</span>
                </div>
              `})}
          </div>
        `:l`<div class="no-schedules">${n("schedule.no_schedules",e)}</div>`}

      <div class="view-temps">
        ${n("schedule.view_comfort",e,{temp:this.comfortTemp.toFixed(1),unit:C(this.useImperial)})}
        \u00A0\u00B7\u00A0
        ${n("schedule.view_eco",e,{temp:this.ecoTemp.toFixed(1),unit:C(this.useImperial)})}
      </div>

      ${this.scheduleSelectorEntity?l`<div class="view-selector-info">
            ${n("schedule.view_selector_prefix",e)}
            <span class="schedule-link" @click=${()=>we(this,this.scheduleSelectorEntity)}>${((a=(o=(s=(i=this.hass)==null?void 0:i.states)==null?void 0:s[this.scheduleSelectorEntity])==null?void 0:o.attributes)==null?void 0:a.friendly_name)||this.scheduleSelectorEntity}</span>
          </div>`:h}
    `}_renderEditMode(){const e=this.hass.language,t=this.schedules.length>=2;return l`
      ${this._renderSelectorSection()}
      ${this._renderScheduleList(t)}
      ${this._renderAddSchedule()}

      <div class="temp-inputs">
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${n("schedule.comfort_label",e)}
            .suffix=${C(this.useImperial)}
            .value=${String(this.comfortTemp.toFixed(1))}
            step=${this.useImperial?"1":"0.5"}
            min=${this.useImperial?"41":"5"}
            max=${this.useImperial?"95":"35"}
            @change=${this._onComfortTempChange}
          ></ha-textfield>
        </div>
        <div class="temp-input-group">
          <ha-textfield
            type="number"
            label=${n("schedule.eco_label",e)}
            .suffix=${C(this.useImperial)}
            .value=${String(this.ecoTemp.toFixed(1))}
            step=${this.useImperial?"1":"0.5"}
            min=${this.useImperial?"41":"5"}
            max=${this.useImperial?"95":"35"}
            @change=${this._onEcoTempChange}
          ></ha-textfield>
        </div>
      </div>
      <div class="fallback-hint">
        ${n("schedule.comfort_hint",e)}
      </div>

      <ha-expansion-panel outlined header=${n("schedule.help_header",e)}>
        <div class="help-content">
          <p><strong>${n("schedule.help_temps_title",e)}</strong></p>
          <p>${n("schedule.help_temps",e)}</p>
          <ol style="margin: 4px 0 0 0; padding-left: 20px; font-size: 12px; line-height: 1.8">
            <li>${oe(n("schedule.help_temps_1",e))}</li>
            <li>${oe(n("schedule.help_temps_2",e))}</li>
            <li>${oe(n("schedule.help_temps_3",e))}</li>
            <li>${oe(n("schedule.help_temps_4",e))}</li>
          </ol>

          <p style="margin-top: 12px"><strong>${n("schedule.help_block_title",e)}</strong></p>
          <p>${oe(n("schedule.help_block",e))}</p>
          <div class="yaml-block"><span class="yaml-key">schedule</span>:
  <span class="yaml-key">living_room_heating</span>:
    <span class="yaml-key">name</span>: <span class="yaml-value">Living Room Heating</span>
    <span class="yaml-key">monday</span>:
      - <span class="yaml-key">from</span>: <span class="yaml-value">"06:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"08:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">23</span>
      - <span class="yaml-key">from</span>: <span class="yaml-value">"17:00:00"</span>
        <span class="yaml-key">to</span>: <span class="yaml-value">"22:00:00"</span>
        <span class="yaml-key">data</span>:
          <span class="yaml-key">temperature</span>: <span class="yaml-value">21.5</span></div>
          <p style="margin-top: 8px">${oe(n("schedule.help_block_note",e))}</p>

          <p style="margin-top: 12px"><strong>${n("schedule.help_multi_title",e)}</strong></p>
          <p>${oe(n("schedule.help_multi",e))}</p>
        </div>
      </ha-expansion-panel>

    `}_renderSelectorSection(){var s,o;const e=this.hass.language;if(!(this.schedules.length>0))return h;const i=this.scheduleSelectorEntity?(o=(s=this.hass)==null?void 0:s.states)==null?void 0:o[this.scheduleSelectorEntity]:null;return l`
      <div class="selector-section">
        <label class="form-label">${n("schedule.selector_label",e)}</label>
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this.scheduleSelectorEntity}
          .includeDomains=${["input_boolean","input_number"]}
          allow-custom-entity
          @value-changed=${this._onSelectorEntityChange}
        ></ha-entity-picker>
        ${this.scheduleSelectorEntity&&i?l`
                <div class="selector-value">
                  ${this.scheduleSelectorEntity.startsWith("input_boolean.")?n("schedule.selector_value_boolean",e,{value:i.state==="on"?"On":"Off"}):n("schedule.selector_value_number",e,{value:i.state})}
                </div>
              `:h}
        ${this.schedules.length>1&&!this.scheduleSelectorEntity?l`
              <div class="selector-warning">
                <ha-icon icon="mdi:alert-outline"></ha-icon>
                ${n("schedule.selector_warning",e)}
              </div>
            `:h}
      </div>
    `}_renderScheduleList(e){const t=this.hass.language;return this.schedules.length===0?l`<div class="no-schedules">${n("schedule.no_schedules",t)}</div>`:l`
      <div class="schedule-list">
        ${this.schedules.map((i,s)=>{var p,c,d;const o=this._getScheduleState(s),a=(c=(p=this.hass)==null?void 0:p.states)==null?void 0:c[i.entity_id],r=((d=a==null?void 0:a.attributes)==null?void 0:d.friendly_name)||i.entity_id;return l`
            <div class="schedule-row ${o}">
              ${e?l`<span class="schedule-number">${s+1}</span>`:h}
              <span class="schedule-status-dot"></span>
              <span class="schedule-name">${r}</span>
              <span class="schedule-status">${this._getStatusText(s,o)}</span>
              <span class="schedule-controls">
                ${e&&s>0?l`
                      <ha-icon-button
                        .path=${"M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"}
                        @click=${()=>this._onMoveSchedule(s,-1)}
                      ></ha-icon-button>
                    `:h}
                ${e&&s<this.schedules.length-1?l`
                      <ha-icon-button
                        .path=${"M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z"}
                        @click=${()=>this._onMoveSchedule(s,1)}
                      ></ha-icon-button>
                    `:h}
                <ha-icon-button
                  .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                  @click=${()=>this._onRemoveSchedule(s)}
                ></ha-icon-button>
              </span>
            </div>
          `})}
      </div>
    `}_renderAddSchedule(){const e=this.hass.language,t=this._getAvailableScheduleEntities();return l`
      <div class="add-schedule-row">
        <ha-select
          .value=${""}
          @selected=${this._onAddSchedule}
          @closed=${i=>i.stopPropagation()}
          fixedMenuPosition
          naturalMenuWidth
        >
          <ha-list-item value="">
            <ha-icon icon="mdi:plus" slot="graphic"></ha-icon>
            ${n("schedule.add_schedule",e)}
          </ha-list-item>
          ${t.map(i=>{var a;const s=this.hass.states[i],o=((a=s==null?void 0:s.attributes)==null?void 0:a.friendly_name)||i;return l`
              <ha-list-item value=${i}>
                ${o}
              </ha-list-item>
            `})}
        </ha-select>
      </div>
    `}_getScheduleState(e){var i,s,o,a;if(this.schedules.length===0)return"inactive";if(e===this.activeScheduleIndex)return"active";if(!this.scheduleSelectorEntity)return e===0?"active":"unreachable";const t=(s=(i=this.hass)==null?void 0:i.states)==null?void 0:s[this.scheduleSelectorEntity];if(!t)return"inactive";if(this.scheduleSelectorEntity.startsWith("input_boolean."))return e<=1?"inactive":"unreachable";if(this.scheduleSelectorEntity.startsWith("input_number.")){const r=Number(((o=t.attributes)==null?void 0:o.min)??1),p=Number(((a=t.attributes)==null?void 0:a.max)??this.schedules.length),c=e+1;return c>=r&&c<=p?"inactive":"unreachable"}return"inactive"}_getStatusText(e,t){var r,p,c;const i=this.hass.language;if(t==="unreachable")return n("schedule.state_unreachable",i);if(t==="inactive")return n("schedule.state_inactive",i);const s=this.schedules[e],o=(p=(r=this.hass)==null?void 0:r.states)==null?void 0:p[s.entity_id];if(!o)return n("schedule.state_active",i);if(o.state==="on"){const d=(c=o.attributes)==null?void 0:c.temperature;return d!=null?n("schedule.from_schedule",i,{temp:d.toFixed(1),unit:C(this.useImperial)}):n("schedule.fallback",i,{temp:this.comfortTemp.toFixed(1),unit:C(this.useImperial)})}return n("schedule.eco_detail",i,{temp:this.ecoTemp.toFixed(1),unit:C(this.useImperial)})}_getScheduleEntities(){var e;return(e=this.hass)!=null&&e.states?Object.keys(this.hass.states).filter(t=>t.startsWith("schedule.")):[]}_getAvailableScheduleEntities(){const e=this._getScheduleEntities(),t=new Set(this.schedules.map(i=>i.entity_id));return e.filter(i=>!t.has(i))}_onAddSchedule(e){const t=e.target,i=t.value;if(!i)return;const s=[...this.schedules,{entity_id:i}];this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:s},bubbles:!0,composed:!0})),requestAnimationFrame(()=>{t.value=""})}_onRemoveSchedule(e){const t=this.schedules.filter((i,s)=>s!==e);this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onMoveSchedule(e,t){const i=e+t;if(i<0||i>=this.schedules.length)return;const s=[...this.schedules],o=s[e];s[e]=s[i],s[i]=o,this.dispatchEvent(new CustomEvent("schedules-changed",{detail:{value:s},bubbles:!0,composed:!0}))}_onSelectorEntityChange(e){var i;const t=((i=e.detail)==null?void 0:i.value)??"";this.dispatchEvent(new CustomEvent("schedule-selector-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onComfortTempChange(e){const t=e.target,i=parseFloat(t.value)||(this.useImperial?70:21);this.dispatchEvent(new CustomEvent("comfort-temp-changed",{detail:{value:i},bubbles:!0,composed:!0}))}_onEcoTempChange(e){const t=e.target,i=parseFloat(t.value)||(this.useImperial?63:17);this.dispatchEvent(new CustomEvent("eco-temp-changed",{detail:{value:i},bubbles:!0,composed:!0}))}};W.styles=O`
    :host {
      display: block;
    }

    .form-group {
      margin-bottom: 16px;
    }

    .form-group:last-child {
      margin-bottom: 0;
    }

    .form-label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    ha-select {
      width: 100%;
    }

    /* Selector section */
    .selector-section {
      margin-bottom: 16px;
    }

    .selector-value {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      padding-left: 4px;
    }

    .selector-warning {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding: 10px 14px;
      border-radius: 8px;
      background: rgba(255, 152, 0, 0.08);
      color: var(--warning-color, #ff9800);
      font-size: 13px;
    }

    .selector-warning ha-icon {
      --mdc-icon-size: 18px;
      flex-shrink: 0;
    }

    /* Schedule list */
    .schedule-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 12px;
    }

    .schedule-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s, opacity 0.3s;
    }

    .schedule-row.active {
      background: rgba(76, 175, 80, 0.1);
    }

    .schedule-row.inactive {
      background: rgba(0, 0, 0, 0.04);
    }

    .schedule-row.unreachable {
      background: rgba(0, 0, 0, 0.02);
      opacity: 0.4;
    }

    .schedule-number {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 500;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--divider-color, #e0e0e0);
      color: var(--primary-text-color);
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-number {
      background: #4caf50;
      color: #fff;
    }

    .schedule-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .schedule-row.active .schedule-status-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .schedule-row.inactive .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-row.unreachable .schedule-status-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .schedule-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .schedule-link {
      cursor: pointer;
    }

    .schedule-link:hover {
      text-decoration: underline;
    }

    .schedule-row.active .schedule-name {
      color: var(--primary-text-color);
    }

    .schedule-row.inactive .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-name {
      color: var(--secondary-text-color);
    }

    .schedule-status {
      font-size: 12px;
      white-space: nowrap;
    }

    .schedule-row.active .schedule-status {
      color: #2e7d32;
    }

    .schedule-row.inactive .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-row.unreachable .schedule-status {
      color: var(--secondary-text-color);
    }

    .schedule-controls {
      display: flex;
      align-items: center;
      gap: 2px;
      flex-shrink: 0;
    }

    .schedule-controls ha-icon-button {
      --mdc-icon-button-size: 28px;
      --mdc-icon-size: 16px;
    }

    /* Add schedule row */
    .add-schedule-row {
      margin-top: 4px;
    }

    .add-schedule-row ha-select {
      width: 100%;
    }

    /* No schedules */
    .no-schedules {
      font-size: 13px;
      color: var(--secondary-text-color);
      padding: 12px 0;
      text-align: center;
    }

    /* Collapsible help */
    ha-expansion-panel {
      margin-top: 8px;
    }

    .help-content {
      padding: 0 12px 12px;
      font-size: 12px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }

    .help-content p {
      margin: 0 0 8px 0;
    }

    .help-content p:last-child {
      margin-bottom: 0;
    }

    .yaml-block {
      background: var(--primary-background-color, #f5f5f5);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: var(--code-font-family, monospace);
      font-size: 12px;
      line-height: 1.5;
      white-space: pre;
      overflow-x: auto;
      color: var(--primary-text-color);
    }

    .yaml-comment {
      color: var(--secondary-text-color);
    }

    .yaml-key {
      color: #0550ae;
    }

    .yaml-value {
      color: #0a3069;
    }

    .fallback-hint {
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 4px;
      font-style: italic;
    }

    .temp-inputs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }

    .temp-input-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    ha-textfield {
      flex: 1;
    }

    /* View mode */
    .view-temps {
      display: flex;
      gap: 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .view-temps span {
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .view-selector-info {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 8px;
    }



  `,K([_({attribute:!1})],W.prototype,"hass",2),K([_({attribute:!1})],W.prototype,"schedules",2),K([_({type:String})],W.prototype,"scheduleSelectorEntity",2),K([_({type:Number})],W.prototype,"activeScheduleIndex",2),K([_({type:Number})],W.prototype,"comfortTemp",2),K([_({type:Number})],W.prototype,"ecoTemp",2),K([_({type:Boolean})],W.prototype,"editing",2),K([_({type:Boolean})],W.prototype,"useImperial",2),W=K([U("rs-schedule-settings")],W);var Vt=Object.defineProperty,jt=Object.getOwnPropertyDescriptor,F=(e,t,i,s)=>{for(var o=s>1?void 0:s?jt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Vt(t,i,o),o};let H=class extends I{constructor(){super(...arguments),this.selectedThermostats=new Set,this.selectedAcs=new Set,this.selectedTempSensor="",this.selectedHumiditySensor="",this.selectedWindowSensors=new Set,this.windowOpenDelay=0,this.windowCloseDelay=0,this.editing=!1,this._entityFilter=e=>{var i,s,o,a;const t=e.entity_id;if(this.selectedThermostats.has(t)||this.selectedAcs.has(t)||this.selectedTempSensor===t||this.selectedHumiditySensor===t||this.selectedWindowSensors.has(t))return!1;if(t.startsWith("sensor.")){const r=(s=(i=this.hass.states[t])==null?void 0:i.attributes)==null?void 0:s.device_class;if(r!=="temperature"&&r!=="humidity")return!1}if(t.startsWith("binary_sensor.")){const r=(a=(o=this.hass.states[t])==null?void 0:o.attributes)==null?void 0:a.device_class;if(r!=="window"&&r!=="door")return!1}return!0}}render(){return this.editing?this._renderEditMode():this._renderViewMode()}_renderViewMode(){const e=this.selectedThermostats.size>0||this.selectedAcs.size>0,t=!!this.selectedTempSensor,i=!!this.selectedHumiditySensor;return l`
      ${e?l`
        <div class="device-group">
          <div class="section-subtitle">${n("devices.climate_entities",this.hass.language)}</div>
          ${[...this.selectedThermostats].map(s=>this._renderViewRow(s,"climate"))}
          ${[...this.selectedAcs].map(s=>this._renderViewRow(s,"climate"))}
        </div>
      `:h}

      ${t?l`
        <div class="device-group">
          <div class="section-subtitle">${n("devices.temp_sensors",this.hass.language)}</div>
          ${this._renderViewRow(this.selectedTempSensor,"temp")}
        </div>
      `:h}

      ${i?l`
        <div class="device-group">
          <div class="section-subtitle">${n("devices.humidity_sensors",this.hass.language)}</div>
          ${this._renderViewRow(this.selectedHumiditySensor,"humidity")}
        </div>
      `:h}

      ${this.selectedWindowSensors.size>0?l`
        <div class="device-group">
          <div class="section-subtitle">${n("devices.window_sensors",this.hass.language)}</div>
          ${[...this.selectedWindowSensors].map(s=>this._renderWindowViewRow(s))}
          ${this.windowOpenDelay||this.windowCloseDelay?l`
            <div class="delay-view">
              ${this.windowOpenDelay?l`${n("devices.window_open_delay",this.hass.language)}: ${this.windowOpenDelay}s`:h}
              ${this.windowOpenDelay&&this.windowCloseDelay?" · ":h}
              ${this.windowCloseDelay?l`${n("devices.window_close_delay",this.hass.language)}: ${this.windowCloseDelay}s`:h}
            </div>
          `:h}
        </div>
      `:h}
    `}_renderViewRow(e,t){var p;const i=this.hass.states[e],s=((p=i==null?void 0:i.attributes)==null?void 0:p.friendly_name)||e,o=i==null?void 0:i.state,a=(i==null?void 0:i.attributes)??{};let r="";if(t==="climate"){const c=a.current_temperature;c!=null&&(r=`${c.toFixed(1)}°`)}else if(t==="temp"){if(o&&o!=="unknown"&&o!=="unavailable"){const c=a.unit_of_measurement??"";r=`${Number(o).toFixed(1)}${c}`}}else o&&o!=="unknown"&&o!=="unavailable"&&(r=`${Math.round(Number(o))}%`);return l`
      <div class="view-row">
        <span class="view-name entity-link" @click=${()=>we(this,e)}>${s}</span>
        ${r?l`<span class="view-value">${r}</span>`:h}
      </div>
    `}_renderWindowViewRow(e){var o;const t=this.hass.states[e],i=((o=t==null?void 0:t.attributes)==null?void 0:o.friendly_name)||e,s=(t==null?void 0:t.state)==="on";return l`
      <div class="view-row">
        <span class="view-name entity-link" @click=${()=>we(this,e)}>${i}</span>
        <span class="view-value" style="color: ${s?"var(--warning-color, #ff9800)":"var(--secondary-text-color)"}">
          ${s?"●":"○"}
        </span>
      </div>
    `}_renderEditMode(){var E,k,$,M,J;const e=Ge(this.area.area_id,(E=this.hass)==null?void 0:E.entities,(k=this.hass)==null?void 0:k.devices),t=e.filter(f=>f.entity_id.startsWith("climate.")),i=($=this.hass)!=null&&$.states?e.filter(f=>{var T,R;return f.entity_id.startsWith("sensor.")&&((R=(T=this.hass.states[f.entity_id])==null?void 0:T.attributes)==null?void 0:R.device_class)==="temperature"}):[],s=(M=this.hass)!=null&&M.states?e.filter(f=>{var T,R;return f.entity_id.startsWith("sensor.")&&((R=(T=this.hass.states[f.entity_id])==null?void 0:T.attributes)==null?void 0:R.device_class)==="humidity"}):[],o=(J=this.hass)!=null&&J.states?e.filter(f=>{var T,R;return f.entity_id.startsWith("binary_sensor.")&&["window","door"].includes((R=(T=this.hass.states[f.entity_id])==null?void 0:T.attributes)==null?void 0:R.device_class)}):[],a=new Set(t.map(f=>f.entity_id)),p=[...new Set([...this.selectedThermostats,...this.selectedAcs])].filter(f=>!a.has(f)),c=new Set(i.map(f=>f.entity_id)),d=this.selectedTempSensor&&!c.has(this.selectedTempSensor)?this.selectedTempSensor:null,g=new Set(s.map(f=>f.entity_id)),m=this.selectedHumiditySensor&&!g.has(this.selectedHumiditySensor)?this.selectedHumiditySensor:null,v=new Set(o.map(f=>f.entity_id)),y=[...this.selectedWindowSensors].filter(f=>!v.has(f));return l`
      <div class="device-group">
        <div class="section-subtitle">${n("devices.climate_entities",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${t.length>0?t.map(f=>this._renderClimateRow(f.entity_id,!1)):l`<div class="no-devices">
                ${n("devices.no_climate",this.hass.language)}
              </div>`}
          ${p.map(f=>this._renderClimateRow(f,!0))}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${n("devices.temp_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${i.length>0?i.map(f=>this._renderSensorRow(f.entity_id,"temp",!1)):l`<div class="no-devices">
                ${n("devices.no_temp_sensors",this.hass.language)}
              </div>`}
          ${d?this._renderSensorRow(d,"temp",!0):h}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${n("devices.humidity_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${s.length>0?s.map(f=>this._renderSensorRow(f.entity_id,"humidity",!1)):l`<div class="no-devices">
                ${n("devices.no_humidity_sensors",this.hass.language)}
              </div>`}
          ${m?this._renderSensorRow(m,"humidity",!0):h}
        </div>
      </div>

      <div class="device-group">
        <div class="section-subtitle">${n("devices.window_sensors",this.hass.language)}</div>
        <div class="device-list-scroll">
          ${o.length>0?o.map(f=>this._renderWindowRow(f.entity_id,!1)):l`<div class="no-devices">
                ${n("devices.no_window_sensors",this.hass.language)}
            </div>`}
          ${y.map(f=>this._renderWindowRow(f,!0))}
        </div>
        ${this.selectedWindowSensors.size>0?l`
          <div class="delay-fields">
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${n("devices.window_open_delay",this.hass.language)}
              .value=${String(this.windowOpenDelay)}
              @change=${this._onWindowOpenDelayChange}
            ></ha-textfield>
            <ha-textfield
              type="number"
              min="0"
              suffix="s"
              .label=${n("devices.window_close_delay",this.hass.language)}
              .value=${String(this.windowCloseDelay)}
              @change=${this._onWindowCloseDelayChange}
            ></ha-textfield>
          </div>
        `:h}
      </div>

      <div class="entity-picker-wrap">
        <ha-entity-picker
          .hass=${this.hass}
          .includeDomains=${["climate","sensor","binary_sensor"]}
          .entityFilter=${this._entityFilter}
          .value=${""}
          label=${n("devices.add_entity",this.hass.language)}
          @value-changed=${this._onEntityPicked}
        ></ha-entity-picker>
      </div>

    `}_renderClimateRow(e,t){var d,g;const i=this.selectedThermostats.has(e),s=this.selectedAcs.has(e),o=i||s,a=this.hass.states[e],r=((d=a==null?void 0:a.attributes)==null?void 0:d.friendly_name)||e,p=a==null?void 0:a.state,c=(g=a==null?void 0:a.attributes)==null?void 0:g.current_temperature;return l`
      <div class="device-row ${o?"selected":""}">
        <ha-checkbox
          .checked=${o}
          @change=${m=>{const v=m.target;this._onClimateToggle(e,v.checked)}}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${r}</span>
            ${t?l`<span class="external-badge">${n("devices.other_area",this.hass.language)}</span>`:h}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        ${c!=null?l`<span class="device-value"
              >${c.toFixed(1)}\u00B0</span
            >`:p&&p!=="unavailable"?l`<span
                class="device-value"
                style="font-size:12px; opacity:0.6"
                >${p}</span
              >`:h}
        ${o?l`
              <ha-select
                class="device-type-select"
                outlined
                .value=${s?"ac":"thermostat"}
                @selected=${m=>{const v=m.target;this._onDeviceTypeChange(e,v.value)}}
                @closed=${m=>m.stopPropagation()}
                fixedMenuPosition
              >
                <ha-list-item value="thermostat">${n("devices.type_thermostat",this.hass.language)}</ha-list-item>
                <ha-list-item value="ac">${n("devices.type_ac",this.hass.language)}</ha-list-item>
              </ha-select>
            `:h}
      </div>
    `}_renderSensorRow(e,t,i){var g,m;const s=this.hass.states[e],o=((g=s==null?void 0:s.attributes)==null?void 0:g.friendly_name)||e,a=s==null?void 0:s.state,p=(t==="temp"?this.selectedTempSensor:this.selectedHumiditySensor)===e,c=t==="temp"?((m=s==null?void 0:s.attributes)==null?void 0:m.unit_of_measurement)??"":"%",d=a&&a!=="unknown"&&a!=="unavailable";return l`
      <div class="device-row ${p?"selected":""}">
        <ha-radio
          .checked=${p}
          name="${t}-sensor"
          @change=${()=>this._onSensorSelected(e,t)}
        ></ha-radio>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${o}</span>
            ${i?l`<span class="external-badge">${n("devices.other_area",this.hass.language)}</span>`:h}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        ${d?l`<span class="device-value">${t==="humidity"?Math.round(Number(a)):Number(a).toFixed(1)}${c}</span>`:h}
      </div>
    `}_renderWindowRow(e,t){var r;const i=this.selectedWindowSensors.has(e),s=this.hass.states[e],o=((r=s==null?void 0:s.attributes)==null?void 0:r.friendly_name)||e,a=(s==null?void 0:s.state)==="on";return l`
      <div class="device-row ${i?"selected":""}">
        <ha-checkbox
          .checked=${i}
          @change=${p=>{const c=p.target;this._onWindowSensorToggle(e,c.checked)}}
        ></ha-checkbox>
        <div class="device-info">
          <div class="device-name-row">
            <span class="device-name">${o}</span>
            ${t?l`<span class="external-badge">${n("devices.other_area",this.hass.language)}</span>`:h}
          </div>
          <div class="device-entity">${e}</div>
        </div>
        <span class="device-value" style="color: ${a?"var(--warning-color, #ff9800)":"var(--secondary-text-color)"}">
          ${a?"●":"○"}
        </span>
      </div>
    `}_detectClimateType(e){var s,o;const t=(o=(s=this.hass.states[e])==null?void 0:s.attributes)==null?void 0:o.hvac_modes;return t&&(t.includes("cool")||t.includes("heat_cool"))?"ac":"thermostat"}_onClimateToggle(e,t){this.dispatchEvent(new CustomEvent("climate-toggle",{detail:{entityId:e,checked:t,detectedType:this._detectClimateType(e)},bubbles:!0,composed:!0}))}_onDeviceTypeChange(e,t){this.dispatchEvent(new CustomEvent("device-type-change",{detail:{entityId:e,type:t},bubbles:!0,composed:!0}))}_onSensorSelected(e,t){this.dispatchEvent(new CustomEvent("sensor-selected",{detail:{entityId:e,type:t},bubbles:!0,composed:!0}))}_onWindowSensorToggle(e,t){this.dispatchEvent(new CustomEvent("window-sensor-toggle",{detail:{entityId:e,checked:t},bubbles:!0,composed:!0}))}_onWindowOpenDelayChange(e){const t=Math.max(0,parseInt(e.target.value)||0);this.dispatchEvent(new CustomEvent("window-open-delay-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onWindowCloseDelayChange(e){const t=Math.max(0,parseInt(e.target.value)||0);this.dispatchEvent(new CustomEvent("window-close-delay-changed",{detail:{value:t},bubbles:!0,composed:!0}))}_onEntityPicked(e){var a,r,p;const t=(a=e.detail)==null?void 0:a.value;if(!t)return;let i;t.startsWith("climate.")?i="climate":t.startsWith("binary_sensor.")?i="window":i=((p=(r=this.hass.states[t])==null?void 0:r.attributes)==null?void 0:p.device_class)==="humidity"?"humidity":"temp";const s=i==="climate"?this._detectClimateType(t):void 0;this.dispatchEvent(new CustomEvent("external-entity-added",{detail:{entityId:t,category:i,detectedType:s},bubbles:!0,composed:!0}));const o=e.target;o.value=""}};H.styles=O`
    :host {
      display: block;
    }

    .section-subtitle {
      font-size: 12px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin: 12px 0 8px 0;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    .section-subtitle:first-child {
      margin-top: 0;
    }

    .device-group {
      padding: 4px 0;
    }

    .device-group + .device-group {
      margin-top: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    .device-list-scroll {
      max-height: 168px;
      overflow-y: auto;
      overflow-x: hidden;
      scrollbar-width: thin;
    }

    /* Device rows */
    .device-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 14px;
      font-size: 14px;
      color: var(--primary-text-color);
      border-radius: 10px;
      margin-bottom: 2px;
      transition: background 0.15s;
    }

    .device-row:last-child {
      margin-bottom: 0;
    }

    .device-row:hover {
      background: rgba(0, 0, 0, 0.02);
    }

    .device-row.selected {
      background: rgba(3, 169, 244, 0.035);
    }

    .device-row ha-checkbox,
    .device-row ha-radio {
      flex-shrink: 0;
    }

    .device-info {
      flex: 1;
      min-width: 0;
    }

    .device-name-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .device-name {
      font-size: 14px;
      font-weight: 450;
      color: var(--primary-text-color);
    }

    .device-value {
      margin-left: auto;
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
      flex-shrink: 0;
    }

    .device-entity {
      font-family: var(--code-font-family, monospace);
      font-size: 11px;
      color: var(--secondary-text-color);
      margin-top: 2px;
      opacity: 0.7;
    }

    .external-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 10px;
      font-weight: 500;
      color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.1);
      padding: 2px 8px;
      border-radius: 10px;
      letter-spacing: 0.3px;
      text-transform: uppercase;
      flex-shrink: 0;
    }

    .device-type-select {
      flex-shrink: 0;
      --ha-select-min-width: 90px;
    }

    .no-devices {
      color: var(--secondary-text-color);
      font-size: 13px;
      font-style: italic;
      padding: 12px 14px;
    }

    .entity-picker-wrap {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--divider-color, #eee);
    }

    ha-entity-picker {
      width: 100%;
    }

    /* View mode styles */
    .view-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 14px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .view-name {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .entity-link {
      cursor: pointer;
    }

    .entity-link:hover {
      text-decoration: underline;
    }

    .view-value {
      font-weight: 500;
      flex-shrink: 0;
    }

    .delay-fields {
      display: flex;
      gap: 12px;
      margin-top: 8px;
      padding: 0 14px;
    }

    .delay-fields ha-textfield {
      flex: 1;
    }

    .delay-view {
      font-size: 12px;
      color: var(--secondary-text-color);
      padding: 4px 14px 0;
    }
  `,F([_({attribute:!1})],H.prototype,"hass",2),F([_({attribute:!1})],H.prototype,"area",2),F([_({attribute:!1})],H.prototype,"selectedThermostats",2),F([_({attribute:!1})],H.prototype,"selectedAcs",2),F([_({type:String})],H.prototype,"selectedTempSensor",2),F([_({type:String})],H.prototype,"selectedHumiditySensor",2),F([_({attribute:!1})],H.prototype,"selectedWindowSensors",2),F([_({type:Number})],H.prototype,"windowOpenDelay",2),F([_({type:Number})],H.prototype,"windowCloseDelay",2),F([_({type:Boolean})],H.prototype,"editing",2),H=F([U("rs-device-section")],H);const Xe=O`
  .info-icon {
    --mdc-icon-size: 16px;
    color: var(--secondary-text-color);
    opacity: 0.3;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s, color 0.15s;
  }

  .info-icon:hover {
    opacity: 0.7;
  }

  .info-icon.info-active {
    opacity: 1;
    color: var(--primary-color);
  }

  .info-panel {
    padding: 12px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
    font-size: 13px;
    line-height: 1.6;
    color: var(--secondary-text-color);
  }

  .info-panel strong {
    display: block;
    margin-bottom: 4px;
    color: var(--primary-text-color);
    font-size: 13px;
  }
`;var Bt=Object.defineProperty,Kt=Object.getOwnPropertyDescriptor,Y=(e,t,i,s)=>{for(var o=s>1?void 0:s?Kt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Bt(t,i,o),o};const Zt="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",Gt="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z";let j=class extends I{constructor(){super(...arguments),this.icon="",this.heading="",this.editable=!1,this.editing=!1,this.doneLabel="",this.hasInfo=!1,this._infoExpanded=!1}render(){return l`
      <ha-card>
        <div class="section-header">
          <ha-icon class="section-icon" icon=${this.icon}></ha-icon>
          <h3 class="section-title">${this.heading}</h3>
          ${this.hasInfo?l`
                <ha-icon
                  class="info-icon ${this._infoExpanded?"info-active":""}"
                  icon="mdi:information-outline"
                  @click=${this._toggleInfo}
                ></ha-icon>
              `:h}
          ${this.editable&&!this.editing?l`
                <ha-icon-button
                  class="edit-btn"
                  .path=${Zt}
                  @click=${this._onEditClick}
                ></ha-icon-button>
              `:h}
          ${this.editable&&this.editing?l`
                <button class="done-btn" @click=${this._onDoneClick}>
                  <ha-icon-button
                    style="--mdc-icon-button-size: 20px; --mdc-icon-size: 14px; pointer-events: none;"
                    .path=${Gt}
                  ></ha-icon-button>
                  ${this.doneLabel}
                </button>
              `:h}
        </div>
        ${this._infoExpanded?l`<div class="section-info"><div class="info-panel"><slot name="info"></slot></div></div>`:h}
        <div class="section-body">
          <slot></slot>
        </div>
      </ha-card>
    `}_toggleInfo(){this._infoExpanded=!this._infoExpanded}_onEditClick(){this.dispatchEvent(new CustomEvent("edit-click",{bubbles:!0,composed:!0}))}_onDoneClick(){this.dispatchEvent(new CustomEvent("done-click",{bubbles:!0,composed:!0}))}};j.styles=[Xe,O`
      :host {
        display: block;
      }

      ha-card {
        overflow: hidden;
        min-width: 0;
      }

      .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 16px 20px 12px;
      }

      .section-icon {
        --mdc-icon-size: 18px;
        opacity: 0.7;
      }

      .section-title {
        font-size: 15px;
        font-weight: 500;
        color: var(--primary-text-color);
        margin: 0;
        flex: 1;
      }

      .edit-btn {
        --mdc-icon-button-size: 32px;
        --mdc-icon-size: 18px;
        color: var(--secondary-text-color);
        margin: -4px -8px -4px 0;
      }

      .done-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        background: none;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 16px;
        color: var(--primary-color);
        font-size: 12px;
        font-weight: 500;
        padding: 4px 12px 4px 8px;
        cursor: pointer;
        transition: background 0.15s;
        --mdc-icon-size: 14px;
      }

      .done-btn:hover {
        background: rgba(3, 169, 244, 0.05);
      }

      .section-info {
        padding: 0 20px 8px;
      }

      .section-body {
        padding: 0 20px 20px;
      }
    `],Y([_({type:String})],j.prototype,"icon",2),Y([_({type:String})],j.prototype,"heading",2),Y([_({type:Boolean})],j.prototype,"editable",2),Y([_({type:Boolean})],j.prototype,"editing",2),Y([_({type:String})],j.prototype,"doneLabel",2),Y([_({type:Boolean})],j.prototype,"hasInfo",2),Y([u()],j.prototype,"_infoExpanded",2),j=Y([U("rs-section-card")],j);var qt=Object.defineProperty,Qt=Object.getOwnPropertyDescriptor,S=(e,t,i,s)=>{for(var o=s>1?void 0:s?Qt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&qt(t,i,o),o};let w=class extends I{constructor(){super(...arguments),this.config=null,this.presenceEnabled=!1,this.presencePersons=[],this.useImperial=!1,this._selectedThermostats=new Set,this._selectedAcs=new Set,this._selectedTempSensor="",this._selectedHumiditySensor="",this._selectedWindowSensors=new Set,this._windowOpenDelay=0,this._windowCloseDelay=0,this._climateMode="auto",this._schedules=[],this._scheduleSelectorEntity="",this._comfortTemp=21,this._ecoTemp=17,this._error="",this._dirty=!1,this._overridePending=null,this._overrideCustomTemp=21,this._overrideError="",this._optimisticOverride=null,this._optimisticClear=!1,this._editingSchedule=!1,this._editingDevices=!1,this._editingPresence=!1,this._selectedPresencePersons=[],this._displayName="",this._prevAreaId=null}connectedCallback(){super.connectedCallback(),this._initFromConfig()}disconnectedCallback(){super.disconnectedCallback(),this._saveDebounce&&clearTimeout(this._saveDebounce)}updated(e){var s,o,a;const t=((s=this.config)==null?void 0:s.area_id)??((o=this.area)==null?void 0:o.area_id)??null;if(t!==this._prevAreaId)this._initFromConfig(),this._prevAreaId=t;else if(e.has("config")&&!this._dirty){const r=e.get("config");r==null&&this._initFromConfig()}if(e.has("config")&&((a=this.config)!=null&&a.live)){const r=this.config.live;this._optimisticOverride&&r.override_active&&(this._optimisticOverride=null),this._optimisticClear&&!r.override_active&&(this._optimisticClear=!1)}}_initFromConfig(){this.config?(this._selectedThermostats=new Set(this.config.thermostats),this._selectedAcs=new Set(this.config.acs),this._selectedTempSensor=this.config.temperature_sensor,this._selectedHumiditySensor=this.config.humidity_sensor??"",this._selectedWindowSensors=new Set(this.config.window_sensors??[]),this._windowOpenDelay=this.config.window_open_delay??0,this._windowCloseDelay=this.config.window_close_delay??0,this._climateMode=this.config.climate_mode,this._schedules=this.config.schedules??[],this._scheduleSelectorEntity=this.config.schedule_selector_entity??"",this._comfortTemp=this.config.comfort_temp??21,this._ecoTemp=this.config.eco_temp??17,this._selectedPresencePersons=this.config.presence_persons??[],this._displayName=this.config.display_name??""):(this._selectedThermostats=new Set,this._selectedAcs=new Set,this._selectedTempSensor="",this._selectedHumiditySensor="",this._selectedWindowSensors=new Set,this._windowOpenDelay=0,this._windowCloseDelay=0,this._climateMode="auto",this._schedules=[],this._scheduleSelectorEntity="",this._comfortTemp=21,this._ecoTemp=17,this._selectedPresencePersons=[],this._displayName=""),this._dirty=!1;const e=this._selectedThermostats.size>0||this._selectedAcs.size>0||!!this._selectedTempSensor;this._editingSchedule=this._schedules.length===0,this._editingDevices=!e}render(){var e,t;return this.area?l`
      <div class="detail-layout">
        <div class="col-left">
          <rs-hero-status
            .hass=${this.hass}
            .area=${this.area}
            .config=${this.config}
            .overrideInfo=${this._getEffectiveOverride()}
            .useImperial=${this.useImperial}
            @display-name-changed=${this._onDisplayNameChanged}
          ></rs-hero-status>

          <rs-section-card
            icon="mdi:cog"
            .heading=${n("room.section.climate_mode",this.hass.language)}
            hasInfo
          >
            <div slot="info">
              <b>${n("mode.auto",this.hass.language)}</b> — ${n("mode.auto_desc",this.hass.language)}<br>
              <b>${n("mode.heat_only",this.hass.language)}</b> — ${n("mode.heat_only_desc",this.hass.language)}<br>
              <b>${n("mode.cool_only",this.hass.language)}</b> — ${n("mode.cool_only_desc",this.hass.language)}
            </div>
            <rs-climate-mode-selector
              .climateMode=${this._climateMode}
              .language=${this.hass.language}
              @mode-changed=${this._onModeChanged}
            ></rs-climate-mode-selector>
          </rs-section-card>

          <rs-section-card
            icon="mdi:calendar"
            .heading=${n("room.section.schedule",this.hass.language)}
            editable
            .editing=${this._editingSchedule}
            .doneLabel=${n("schedule.done",this.hass.language)}
            @edit-click=${()=>{this._editingSchedule=!0}}
            @done-click=${()=>{this._editingSchedule=!1}}
          >
            <rs-schedule-settings
              .hass=${this.hass}
              .schedules=${this._schedules}
              .scheduleSelectorEntity=${this._scheduleSelectorEntity}
              .activeScheduleIndex=${((t=(e=this.config)==null?void 0:e.live)==null?void 0:t.active_schedule_index)??-1}
              .comfortTemp=${this._comfortTemp}
              .ecoTemp=${this._ecoTemp}
              .editing=${this._editingSchedule}
              .useImperial=${this.useImperial}
              @schedules-changed=${this._onSchedulesChanged}
              @schedule-selector-changed=${this._onScheduleSelectorChanged}
              @comfort-temp-changed=${this._onComfortTempChanged}
              @eco-temp-changed=${this._onEcoTempChanged}
            ></rs-schedule-settings>
            ${this.config?this._renderOverrideSection():h}
          </rs-section-card>

          ${this._error?l`<div class="error">${this._error}</div>`:h}
        </div>

        <div class="col-right">
          <rs-section-card
            icon="mdi:power-plug"
            .heading=${n("room.section.devices",this.hass.language)}
            editable
            .editing=${this._editingDevices}
            .doneLabel=${n("devices.done",this.hass.language)}
            @edit-click=${()=>{this._editingDevices=!0}}
            @done-click=${()=>{this._editingDevices=!1}}
          >
            <rs-device-section
              .hass=${this.hass}
              .area=${this.area}
              .editing=${this._editingDevices}
              .useImperial=${this.useImperial}
              .selectedThermostats=${this._selectedThermostats}
              .selectedAcs=${this._selectedAcs}
              .selectedTempSensor=${this._selectedTempSensor}
              .selectedHumiditySensor=${this._selectedHumiditySensor}
              .selectedWindowSensors=${this._selectedWindowSensors}
              .windowOpenDelay=${this._windowOpenDelay}
              .windowCloseDelay=${this._windowCloseDelay}
              @climate-toggle=${this._onClimateToggle}
              @device-type-change=${this._onDeviceTypeChange}
              @sensor-selected=${this._onSensorSelected}
              @window-sensor-toggle=${this._onWindowSensorToggle}
              @window-open-delay-changed=${this._onWindowOpenDelayChanged}
              @window-close-delay-changed=${this._onWindowCloseDelayChanged}
              @external-entity-added=${this._onExternalEntityAdded}
            ></rs-device-section>
          </rs-section-card>

          ${this._renderPresenceSection()}
        </div>
      </div>
    `:h}_onModeChanged(e){this._climateMode=e.detail.mode,this._autoSave()}_onSchedulesChanged(e){this._schedules=e.detail.value,this._autoSave()}_onScheduleSelectorChanged(e){this._scheduleSelectorEntity=e.detail.value,this._autoSave()}_onComfortTempChanged(e){this._comfortTemp=e.detail.value,this._autoSave()}_onEcoTempChanged(e){this._ecoTemp=e.detail.value,this._autoSave()}_onClimateToggle(e){const{entityId:t,checked:i,detectedType:s}=e.detail;if(i){const o=new Set(this._selectedThermostats),a=new Set(this._selectedAcs);s==="ac"?a.add(t):o.add(t),this._selectedThermostats=o,this._selectedAcs=a}else{const o=new Set(this._selectedThermostats),a=new Set(this._selectedAcs);o.delete(t),a.delete(t),this._selectedThermostats=o,this._selectedAcs=a}this._autoSave()}_onDeviceTypeChange(e){const{entityId:t,type:i}=e.detail,s=new Set(this._selectedThermostats),o=new Set(this._selectedAcs);i==="thermostat"?(o.delete(t),s.add(t)):(s.delete(t),o.add(t)),this._selectedThermostats=s,this._selectedAcs=o,this._autoSave()}_onSensorSelected(e){e.detail.type==="temp"?this._selectedTempSensor=e.detail.entityId:this._selectedHumiditySensor=e.detail.entityId,this._autoSave()}_onWindowSensorToggle(e){const{entityId:t,checked:i}=e.detail,s=new Set(this._selectedWindowSensors);i?s.add(t):s.delete(t),this._selectedWindowSensors=s,this._autoSave()}_onWindowOpenDelayChanged(e){this._windowOpenDelay=e.detail.value,this._autoSave()}_onWindowCloseDelayChanged(e){this._windowCloseDelay=e.detail.value,this._autoSave()}_onExternalEntityAdded(e){const{entityId:t,category:i,detectedType:s}=e.detail;if(i==="climate"){const o=new Set(this._selectedThermostats),a=new Set(this._selectedAcs);s==="ac"?a.add(t):o.add(t),this._selectedThermostats=o,this._selectedAcs=a}else if(i==="temp")this._selectedTempSensor=t;else if(i==="window"){const o=new Set(this._selectedWindowSensors);o.add(t),this._selectedWindowSensors=o}else this._selectedHumiditySensor=t;this._autoSave()}_onDisplayNameChanged(e){this._displayName=e.detail.value,this._autoSave()}_autoSave(){this._dirty=!0,this._saveDebounce&&clearTimeout(this._saveDebounce),this._saveDebounce=setTimeout(()=>this._doSave(),500)}async _doSave(){L(this,"saving"),this._error="";try{await this.hass.callWS({type:"roommind/rooms/save",area_id:this.area.area_id,thermostats:[...this._selectedThermostats],acs:[...this._selectedAcs],temperature_sensor:this._selectedTempSensor,humidity_sensor:this._selectedHumiditySensor,window_sensors:[...this._selectedWindowSensors],window_open_delay:this._windowOpenDelay,window_close_delay:this._windowCloseDelay,climate_mode:this._climateMode,schedules:this._schedules,schedule_selector_entity:this._scheduleSelectorEntity,comfort_temp:this._comfortTemp,eco_temp:this._ecoTemp,presence_persons:this._selectedPresencePersons.filter(e=>e),display_name:this._displayName}),this._dirty=!1,L(this,"saved"),this.dispatchEvent(new CustomEvent("room-updated",{bubbles:!0,composed:!0}))}catch(e){const t=e instanceof Error?e.message:n("room.error_save_fallback",this.hass.language);this._error=t,L(this,"error")}}_getEffectiveOverride(){var t;if(this._optimisticClear)return{active:!1,type:null,temp:null,until:null};if(this._optimisticOverride)return{active:!0,type:this._optimisticOverride.type,temp:this._optimisticOverride.temp,until:this._optimisticOverride.until};const e=(t=this.config)==null?void 0:t.live;return e!=null&&e.override_active&&e.override_type?{active:!0,type:e.override_type,temp:e.override_temp,until:e.override_until}:{active:!1,type:null,temp:null,until:null}}_renderPresenceSection(){return!this.presenceEnabled||this.presencePersons.length===0?h:l`
      <rs-section-card
        icon="mdi:home-account"
        .heading=${n("room.section.presence",this.hass.language)}
        editable
        .editing=${this._editingPresence}
        .doneLabel=${n("schedule.done",this.hass.language)}
        @edit-click=${()=>{this._editingPresence=!0}}
        @done-click=${()=>{this._editingPresence=!1}}
      >
        ${this._editingPresence?l`
          <div style="padding: 0 16px 16px">
            <div class="presence-chips">
              ${this.presencePersons.map(e=>{var s,o;const t=this._selectedPresencePersons.includes(e),i=((o=(s=this.hass.states[e])==null?void 0:s.attributes)==null?void 0:o.friendly_name)??e.replace("person.","");return l`
                  <button
                    class="presence-chip ${t?"active":""}"
                    @click=${()=>{t?this._selectedPresencePersons=this._selectedPresencePersons.filter(a=>a!==e):this._selectedPresencePersons=[...this._selectedPresencePersons,e],this._autoSave()}}
                  >
                    <ha-icon icon=${t?"mdi:account-check":"mdi:account-outline"} style="--mdc-icon-size: 16px"></ha-icon>
                    ${i}
                  </button>
                `})}
            </div>
            <ha-expansion-panel outlined .header=${n("presence.room_help_header",this.hass.language)} style="margin-top: 12px">
              <div class="help-content">
                <p>${n("presence.room_help_body",this.hass.language)}</p>
              </div>
            </ha-expansion-panel>
          </div>
        `:l`
          <div style="padding: 0 16px 16px">
            ${this._selectedPresencePersons.length>0?l`
              <div class="presence-list">
                ${this._selectedPresencePersons.map(e=>{var s,o,a;const t=((o=(s=this.hass.states[e])==null?void 0:s.attributes)==null?void 0:o.friendly_name)??e.replace("person.",""),i=((a=this.hass.states[e])==null?void 0:a.state)==="home";return l`
                    <div class="presence-row ${i?"home":"away"}">
                      <span class="presence-dot"></span>
                      <span class="presence-name">${t}</span>
                      <span class="presence-state">${i?n("presence.state_home",this.hass.language):n("presence.state_away",this.hass.language)}</span>
                    </div>
                  `})}
              </div>
            `:l`
              <span class="field-hint">${n("presence.room_none_assigned",this.hass.language)}</span>
            `}
          </div>
        `}
      </rs-section-card>
    `}_renderOverrideSection(){const e=this._getEffectiveOverride();return l`
      <hr class="override-divider" />
      <div class="override-label">${n("override.label",this.hass.language)}</div>
      ${this._renderOverrideButtons(e)}
      ${this._overrideError?l`<div class="override-error">${this._overrideError}</div>`:h}
    `}_renderOverrideButtons(e){const t=e.active?e.type:null,i=!t&&this._overridePending;return l`
      <div class="override-presets">
        ${["boost","eco","custom"].map(s=>{const o=t===s,a=t!==null&&!o,r=!t&&this._overridePending===s;return l`
            <button
              class="override-preset ${s} ${o?"active":""} ${r?"pending":""}"
              ?disabled=${a}
              @click=${()=>o?this._onClearOverride():this._onOverridePreset(s)}
            >
              <ha-icon icon=${s==="boost"?"mdi:fire":s==="eco"?"mdi:leaf":"mdi:thermometer"}></ha-icon>
              ${s==="boost"?`${n("override.comfort",this.hass.language)} ${this._comfortTemp.toFixed(1)}${C(this.useImperial)}`:s==="eco"?`${n("override.eco",this.hass.language)} ${this._ecoTemp.toFixed(1)}${C(this.useImperial)}`:n("override.custom",this.hass.language)}
            </button>
          `})}
      </div>
      ${i?l`
            ${this._overridePending==="custom"?l`
                  <div class="override-custom-row">
                    <span>${n("override.target",this.hass.language)}</span>
                    <input
                      type="number"
                      min=${this.useImperial?"41":"5"}
                      max=${this.useImperial?"95":"35"}
                      step=${this.useImperial?"1":"0.5"}
                      .value=${String(this._overrideCustomTemp.toFixed(1))}
                      @input=${this._onOverrideCustomTempInput}
                    />
                    <span>${C(this.useImperial)}</span>
                  </div>
                `:h}
            <div class="override-duration">
              <span class="override-duration-label">${n("override.activate_for",this.hass.language)}</span>
              ${[{label:"1h",hours:1},{label:"2h",hours:2},{label:"4h",hours:4}].map(s=>l`
                  <button
                    class="override-dur-chip"
                    @click=${()=>this._onOverrideActivate(s.hours)}
                  >
                    ${s.label}
                  </button>
                `)}
            </div>
          `:h}
    `}_onOverridePreset(e){this._overridePending===e?this._overridePending=null:(this._overridePending=e,e==="custom"&&(this._overrideCustomTemp=this._comfortTemp)),this._overrideError=""}_onOverrideCustomTempInput(e){this._overrideCustomTemp=Number(e.target.value)||(this.useImperial?70:21)}async _onOverrideActivate(e){if(!this._overridePending||!this.config)return;const t=this._overridePending;let i;t==="boost"?i=this._comfortTemp:t==="eco"?i=this._ecoTemp:i=this._overrideCustomTemp,this._optimisticOverride={type:t,temp:i,until:Date.now()/1e3+e*3600},this._optimisticClear=!1,this._overridePending=null,this._overrideError="";const s={type:"roommind/override/set",area_id:this.config.area_id,override_type:t,duration:e};t==="custom"&&(s.temperature=i);try{await this.hass.callWS(s),this._fireRoomUpdated()}catch(o){this._optimisticOverride=null,this._overrideError=o instanceof Error?o.message:n("override.error_set",this.hass.language),console.error("Override set failed:",o)}}async _onClearOverride(){if(this.config){this._optimisticClear=!0,this._optimisticOverride=null,this._overrideError="";try{await this.hass.callWS({type:"roommind/override/clear",area_id:this.config.area_id}),this._fireRoomUpdated()}catch(e){this._optimisticClear=!1,this._overrideError=e instanceof Error?e.message:n("override.error_clear",this.hass.language),console.error("Override clear failed:",e)}}}_fireRoomUpdated(){this.dispatchEvent(new CustomEvent("room-updated",{bubbles:!0,composed:!0}))}};w.styles=O`
    :host {
      display: block;
      max-width: 1100px;
      margin: 0 auto;
    }

    .detail-layout {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .col-left,
    .col-right {
      display: flex;
      flex-direction: column;
      gap: 16px;
      min-width: 0;
    }

    @media (max-width: 860px) {
      .detail-layout {
        grid-template-columns: 1fr;
      }
    }

    /* Section cards handled by rs-section-card */

    /* Actions */
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 8px;
      margin-bottom: 24px;
    }

    .error {
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      margin-top: 8px;
    }

    /* Override section */
    .override-divider {
      border: none;
      border-top: 1px solid var(--divider-color, #e0e0e0);
      margin: 16px 0 12px;
    }

    .override-label {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 10px;
    }

    .override-presets {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .override-preset {
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 13px;
      background: transparent;
      color: var(--primary-text-color);
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s, border-color 0.15s;
    }

    .override-preset:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .override-preset.pending {
      border-color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .override-preset.active.boost {
      border-color: var(--warning-color, #ff9800);
      background: rgba(255, 152, 0, 0.15);
      color: var(--warning-color, #ff9800);
    }

    .override-preset.active.eco {
      border-color: #4caf50;
      background: rgba(76, 175, 80, 0.15);
      color: #4caf50;
    }

    .override-preset.active.custom {
      border-color: #2196f3;
      background: rgba(33, 150, 243, 0.15);
      color: #2196f3;
    }

    .override-preset:disabled {
      opacity: 0.35;
      cursor: default;
    }

    .override-preset:disabled:hover {
      background: transparent;
    }

    .override-preset ha-icon {
      --mdc-icon-size: 16px;
    }

    .override-duration {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      align-items: center;
    }

    .override-duration-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-dur-chip {
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 12px;
      background: transparent;
      color: var(--primary-text-color);
      transition: background 0.15s;
    }

    .override-dur-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .override-dur-chip:disabled {
      opacity: 0.5;
      pointer-events: none;
    }

    .override-custom-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }

    .override-custom-row input {
      width: 56px;
      padding: 4px 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
      font-size: 13px;
      text-align: center;
      background: transparent;
      color: var(--primary-text-color);
    }

    .override-custom-row span {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .override-error {
      color: var(--error-color, #d32f2f);
      font-size: 12px;
      margin-top: 6px;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .exceptions-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px 0 0;
      margin: 0;
      cursor: pointer;
      font-size: 13px;
      color: var(--primary-color);
      font-family: inherit;
    }

    .exceptions-link:hover {
      text-decoration: underline;
    }

    .presence-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .presence-chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 16px;
      padding: 4px 12px;
      font-size: 13px;
      font-family: inherit;
      background: transparent;
      color: var(--secondary-text-color);
      transition: background 0.15s, border-color 0.15s, color 0.15s;
    }

    .presence-chip:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-chip.active {
      border-color: var(--primary-color);
      color: var(--primary-color);
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.08);
    }

    .presence-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 8px;
      transition: background 0.3s;
    }

    .presence-row.home {
      background: rgba(76, 175, 80, 0.1);
    }

    .presence-row.away {
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .presence-row.home .presence-dot {
      background: #4caf50;
      box-shadow: 0 0 6px rgba(76, 175, 80, 0.5);
    }

    .presence-row.away .presence-dot {
      background: var(--disabled-text-color, #bdbdbd);
    }

    .presence-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .presence-row.home .presence-name {
      color: var(--primary-text-color);
    }

    .presence-row.away .presence-name {
      color: var(--secondary-text-color);
    }

    .presence-state {
      font-size: 12px;
      white-space: nowrap;
    }

    .presence-row.home .presence-state {
      color: #2e7d32;
    }

    .presence-row.away .presence-state {
      color: var(--secondary-text-color);
    }

    .help-content {
      padding: 0 16px 16px;
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.5;
    }
  `,S([_({attribute:!1})],w.prototype,"area",2),S([_({attribute:!1})],w.prototype,"config",2),S([_({attribute:!1})],w.prototype,"hass",2),S([_({type:Boolean})],w.prototype,"presenceEnabled",2),S([_({attribute:!1})],w.prototype,"presencePersons",2),S([_({type:Boolean})],w.prototype,"useImperial",2),S([u()],w.prototype,"_selectedThermostats",2),S([u()],w.prototype,"_selectedAcs",2),S([u()],w.prototype,"_selectedTempSensor",2),S([u()],w.prototype,"_selectedHumiditySensor",2),S([u()],w.prototype,"_selectedWindowSensors",2),S([u()],w.prototype,"_windowOpenDelay",2),S([u()],w.prototype,"_windowCloseDelay",2),S([u()],w.prototype,"_climateMode",2),S([u()],w.prototype,"_schedules",2),S([u()],w.prototype,"_scheduleSelectorEntity",2),S([u()],w.prototype,"_comfortTemp",2),S([u()],w.prototype,"_ecoTemp",2),S([u()],w.prototype,"_error",2),S([u()],w.prototype,"_dirty",2),S([u()],w.prototype,"_overridePending",2),S([u()],w.prototype,"_overrideCustomTemp",2),S([u()],w.prototype,"_overrideError",2),S([u()],w.prototype,"_optimisticOverride",2),S([u()],w.prototype,"_optimisticClear",2),S([u()],w.prototype,"_editingSchedule",2),S([u()],w.prototype,"_editingDevices",2),S([u()],w.prototype,"_editingPresence",2),S([u()],w.prototype,"_selectedPresencePersons",2),S([u()],w.prototype,"_displayName",2),w=S([U("rs-room-detail")],w);const Yt=async()=>{if(!customElements.get("ha-entity-picker")){if(!customElements.get("ha-card")){await customElements.whenDefined("partial-panel-resolver");const e=document.createElement("partial-panel-resolver");e.hass={panels:[{url_path:"tmp",component_name:"config"}]},e._updateRoutes(),await e.routerOptions.routes.tmp.load(),await customElements.whenDefined("ha-panel-config"),await document.createElement("ha-panel-config").routerOptions.routes.automation.load()}if(!customElements.get("ha-entity-picker"))try{await(await(await window.loadCardHelpers()).createCardElement({type:"entities",entities:[]})).constructor.getConfigElement()}catch{}if(await customElements.whenDefined("ha-card"),!customElements.get("ha-date-range-picker"))try{await(await window.loadCardHelpers()).createCardElement({type:"energy-date-selection",entities:[]}),await Promise.race([customElements.whenDefined("ha-date-range-picker"),new Promise((t,i)=>setTimeout(i,5e3))])}catch{}if(!customElements.get("ha-chart-base"))try{await(await window.loadCardHelpers()).createCardElement({type:"statistics-graph",entities:[]}),await Promise.race([customElements.whenDefined("ha-chart-base"),new Promise((t,i)=>setTimeout(i,5e3))])}catch{}}};var Jt=Object.defineProperty,Xt=Object.getOwnPropertyDescriptor,x=(e,t,i,s)=>{for(var o=s>1?void 0:s?Xt(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&Jt(t,i,o),o};let b=class extends I{constructor(){super(...arguments),this.rooms={},this.useImperial=!1,this._climateControlActive=!0,this._learningDisabledRooms=[],this._showLearningExceptions=!1,this._outdoorTempSensor="",this._outdoorHumiditySensor="",this._outdoorCoolingMin=16,this._outdoorHeatingMax=22,this._controlMode="mpc",this._comfortWeight=70,this._weatherEntity="",this._predictionEnabled=!0,this._vacationActive=!1,this._vacationTemp=15,this._vacationUntil="",this._presenceEnabled=!1,this._presencePersons=[],this._valveProtectionEnabled=!1,this._valveProtectionInterval=7,this._moldDetectionEnabled=!1,this._moldHumidityThreshold=70,this._moldSustainedMinutes=30,this._moldNotificationCooldown=60,this._moldNotificationsEnabled=!0,this._moldNotificationTargets=[],this._moldPreventionEnabled=!1,this._moldPreventionIntensity="medium",this._moldPreventionNotify=!1,this._resetSelectedRoom="",this._loaded=!1,this._filterTemperature=e=>{var t;return((t=e.attributes)==null?void 0:t.device_class)==="temperature"},this._filterHumidity=e=>{var t;return((t=e.attributes)==null?void 0:t.device_class)==="humidity"}}connectedCallback(){super.connectedCallback(),this._loadSettings()}disconnectedCallback(){super.disconnectedCallback(),this._saveDebounce&&clearTimeout(this._saveDebounce)}async _loadSettings(){try{const e=await this.hass.callWS({type:"roommind/settings/get"});this._climateControlActive=e.settings.climate_control_active??!0,this._learningDisabledRooms=e.settings.learning_disabled_rooms??[],this._outdoorTempSensor=e.settings.outdoor_temp_sensor??"",this._outdoorHumiditySensor=e.settings.outdoor_humidity_sensor??"",this._outdoorCoolingMin=e.settings.outdoor_cooling_min??16,this._outdoorHeatingMax=e.settings.outdoor_heating_max??22,this._controlMode=e.settings.control_mode??"mpc",this._comfortWeight=e.settings.comfort_weight??70,this._weatherEntity=e.settings.weather_entity??"",this._predictionEnabled=e.settings.prediction_enabled??!0;const t=e.settings.vacation_until;this._vacationActive=!!(t&&t>Date.now()/1e3),this._vacationTemp=e.settings.vacation_temp??15,t&&t>Date.now()/1e3&&(this._vacationUntil=this._tsToDatetimeLocal(t)),this._presenceEnabled=e.settings.presence_enabled??!1,this._presencePersons=e.settings.presence_persons??[],this._valveProtectionEnabled=e.settings.valve_protection_enabled??!1,this._valveProtectionInterval=e.settings.valve_protection_interval_days??7,this._moldDetectionEnabled=e.settings.mold_detection_enabled??!1,this._moldHumidityThreshold=e.settings.mold_humidity_threshold??70,this._moldSustainedMinutes=e.settings.mold_sustained_minutes??30,this._moldNotificationCooldown=e.settings.mold_notification_cooldown??60,this._moldNotificationsEnabled=e.settings.mold_notifications_enabled??!0,this._moldNotificationTargets=e.settings.mold_notification_targets??[],this._moldPreventionEnabled=e.settings.mold_prevention_enabled??!1,this._moldPreventionIntensity=e.settings.mold_prevention_intensity??"medium",this._moldPreventionNotify=e.settings.mold_prevention_notify_enabled??!1}catch(e){console.debug("[RoomMind] loadSettings:",e)}finally{this._loaded=!0}}render(){var p,c;if(!this._loaded)return l`<div class="loading">${n("panel.loading",this.hass.language)}</div>`;const e=this.hass.language,t=this._outdoorTempSensor?this._getSensorValue(this._outdoorTempSensor):null,i=this._outdoorHumiditySensor?this._getSensorValue(this._outdoorHumiditySensor):null,s=Object.entries(this.rooms).map(([d])=>{var g,m;return{areaId:d,name:((m=(g=this.hass.areas)==null?void 0:g[d])==null?void 0:m.name)??d}}).sort((d,g)=>d.name.localeCompare(g.name)),o=Object.keys(this.rooms),a=o.length===0||this._learningDisabledRooms.length<o.length,r=this._learningDisabledRooms.filter(d=>o.includes(d)).length;return l`
      <div class="left-column">
      <!-- Card: General -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:power"></ha-icon>
            <span>${n("settings.general_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${n("settings.climate_control_active",e)}</span>
                <span class="toggle-hint">${n("settings.climate_control_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this._climateControlActive}
                @change=${this._onClimateControlChanged}
              ></ha-switch>
            </div>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${n("settings.learning_title",e)}</span>
                <span class="toggle-hint">${n("settings.learning_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${a}
                @change=${this._onLearningToggled}
              ></ha-switch>
            </div>
            ${a&&s.length>0?l`
                  <button class="exceptions-link" @click=${this._toggleLearningExceptions}>
                    <span>${r>0?`${r} ${n(r===1?"settings.learning_room_paused":"settings.learning_rooms_paused",e)}`:n("settings.learning_exceptions",e)}</span>
                    <ha-icon
                      icon=${this._showLearningExceptions?"mdi:chevron-up":"mdi:chevron-down"}
                      style="--mdc-icon-size: 16px"
                    ></ha-icon>
                  </button>
                  ${this._showLearningExceptions?l`
                        <div class="room-toggles">
                          ${s.map(d=>l`
                              <div class="room-toggle-row">
                                <span class="room-toggle-name">${d.name}</span>
                                <ha-switch
                                  .checked=${!this._learningDisabledRooms.includes(d.areaId)}
                                  @change=${g=>this._onLearningRoomToggled(d.areaId,!g.target.checked)}
                                ></ha-switch>
                              </div>
                            `)}
                        </div>
                      `:h}
                `:h}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:airplane" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${n("vacation.title",e)}
                </span>
                <span class="toggle-hint">${n("vacation.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this._vacationActive}
                @change=${this._onVacationToggled}
              ></ha-switch>
            </div>
            ${this._vacationActive?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${this._vacationUntil}
                        .label=${n("vacation.end_date",e)}
                        type="datetime-local"
                        @change=${this._onVacationUntilChanged}
                      ></ha-textfield>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._vacationTemp.toFixed(1))}
                        .label=${n("vacation.setback_temp",e)}
                        .suffix=${C(this.useImperial)}
                        type="number"
                        step=${this.useImperial?"1":"0.5"}
                        min=${this.useImperial?"41":"5"}
                        max=${this.useImperial?"77":"25"}
                        @change=${this._onVacationTempChanged}
                      ></ha-textfield>
                    </div>
                  </div>
                `:h}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:home-account" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${n("presence.title",e)}
                </span>
                <span class="toggle-hint">${n("presence.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this._presenceEnabled}
                @change=${this._onPresenceToggled}
              ></ha-switch>
            </div>
            ${this._presenceEnabled?l`
                  <div class="room-toggles" style="gap: 8px">
                    <span class="field-hint" style="margin-bottom: 4px">${n("presence.hint_detail",e)}</span>
                    ${this._presencePersons.length>0?l`
                      <div class="presence-person-list">
                        ${this._presencePersons.map(d=>{var m,v;const g=((v=(m=this.hass.states[d])==null?void 0:m.attributes)==null?void 0:v.friendly_name)??d.replace("person.","");return l`
                            <div class="presence-person-row">
                              <ha-icon icon="mdi:account" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                              <span class="presence-person-name">${g}</span>
                              <ha-icon-button
                                .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                                @click=${()=>{this._presencePersons=this._presencePersons.filter(y=>y!==d),this._autoSave()}}
                              ></ha-icon-button>
                            </div>
                          `})}
                      </div>
                    `:h}
                    <ha-entity-picker
                      .hass=${this.hass}
                      .includeDomains=${["person"]}
                      .entityFilter=${d=>!this._presencePersons.includes(d.entity_id)}
                      .label=${n("presence.add_person",e)}
                      @value-changed=${d=>{var v;const g=(v=d.detail)==null?void 0:v.value;g&&!this._presencePersons.includes(g)&&(this._presencePersons=[...this._presencePersons,g],this._autoSave());const m=d.target;m.value=""}}
                    ></ha-entity-picker>
                  </div>
                `:h}
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-refresh" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${n("valve_protection.title",e)}
                </span>
                <span class="toggle-hint">${n("valve_protection.hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this._valveProtectionEnabled}
                @change=${this._onValveProtectionToggled}
              ></ha-switch>
            </div>
            ${this._valveProtectionEnabled?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._valveProtectionInterval)}
                        .label=${n("valve_protection.interval_label",e)}
                        .suffix=${n("valve_protection.interval_suffix",e)}
                        type="number"
                        step="1"
                        min="1"
                        max="90"
                        @change=${this._onValveProtectionIntervalChanged}
                      ></ha-textfield>
                      <span class="field-hint">${n("valve_protection.interval_hint",e)}</span>
                    </div>
                  </div>
                `:h}
          </div>
        </div>
      </ha-card>

      <!-- Card 2: Control -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:tune-variant"></ha-icon>
            <span>${n("settings.control_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <p class="hint">${n("settings.control_mode_hint",e)}</p>
            <div class="radio-group">
              <label class="radio-option" @click=${()=>this._setControlMode("mpc")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this._controlMode==="mpc"}
                ></ha-radio>
                <span>${n("settings.control_mode_mpc",e)}</span>
              </label>
              <label class="radio-option" @click=${()=>this._setControlMode("bangbang")}>
                <ha-radio
                  name="control_mode"
                  .checked=${this._controlMode==="bangbang"}
                ></ha-radio>
                <span>${n("settings.control_mode_simple",e)}</span>
              </label>
            </div>
          </div>

          <div class="settings-section">
            <label class="section-label">${n("settings.comfort_weight",e)}</label>
            <div class="slider-row">
              <span class="slider-label">${n("settings.comfort_weight_efficiency",e)}</span>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                .value=${String(this._comfortWeight)}
                @change=${this._onComfortWeightChanged}
              />
              <span class="slider-label">${n("settings.comfort_weight_comfort",e)}</span>
            </div>
          </div>

          <div class="settings-section">
            <p class="hint">${n("settings.smart_control_hint",e)}</p>
            <div class="threshold-grid">
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(this._outdoorCoolingMin.toFixed(1))}
                  .label=${n("settings.outdoor_cooling_min",e)}
                  .suffix=${C(this.useImperial)}
                  type="number"
                  step="1"
                  min=${this.useImperial?"14":"-10"}
                  max=${this.useImperial?"104":"40"}
                  @change=${this._onOutdoorCoolingMinChanged}
                ></ha-textfield>
                <span class="field-hint">${n("settings.outdoor_cooling_min_hint",e)}</span>
              </div>
              <div class="threshold-field">
                <ha-textfield
                  .value=${String(this._outdoorHeatingMax.toFixed(1))}
                  .label=${n("settings.outdoor_heating_max",e)}
                  .suffix=${C(this.useImperial)}
                  type="number"
                  step="1"
                  min=${this.useImperial?"32":"0"}
                  max=${this.useImperial?"104":"40"}
                  @change=${this._onOutdoorHeatingMaxChanged}
                ></ha-textfield>
                <span class="field-hint">${n("settings.outdoor_heating_max_hint",e)}</span>
              </div>
            </div>
          </div>

          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">${n("settings.prediction_enabled",e)}</span>
                <span class="toggle-hint">${n("settings.prediction_enabled_hint",e)}</span>
              </div>
              <ha-switch
                .checked=${this._predictionEnabled}
                @change=${this._onPredictionEnabledChanged}
              ></ha-switch>
            </div>
          </div>
        </div>
      </ha-card>
      </div>

      <div class="right-column">
      <!-- Card 1: Sensors & Data Sources -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:thermometer"></ha-icon>
            <span>${n("settings.sensors_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <div class="settings-section">
            <div class="sensor-grid">
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this._outdoorTempSensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterTemperature}
                  .label=${n("settings.outdoor_sensor_label",e)}
                  allow-custom-entity
                  @value-changed=${this._onOutdoorTempChanged}
                ></ha-entity-picker>
                ${t!==null?l`<div class="current-value">
                      ${n("settings.outdoor_current",e,{temp:t.toFixed(1),unit:((c=(p=this.hass.states[this._outdoorTempSensor])==null?void 0:p.attributes)==null?void 0:c.unit_of_measurement)??C(this.useImperial)})}
                    </div>`:this._outdoorTempSensor?l`<div class="current-value muted">
                        ${n("settings.outdoor_waiting",e)}
                      </div>`:h}
              </div>
              <div class="sensor-field">
                <ha-entity-picker
                  .hass=${this.hass}
                  .value=${this._outdoorHumiditySensor}
                  .includeDomains=${["sensor"]}
                  .entityFilter=${this._filterHumidity}
                  .label=${n("settings.outdoor_humidity_label",e)}
                  allow-custom-entity
                  @value-changed=${this._onOutdoorHumidityChanged}
                ></ha-entity-picker>
                ${i!==null?l`<div class="current-value">
                      ${n("settings.outdoor_humidity_current",e,{value:String(i)})}
                    </div>`:this._outdoorHumiditySensor?l`<div class="current-value muted">
                        ${n("settings.outdoor_waiting",e)}
                      </div>`:h}
              </div>
            </div>
          </div>

          <div class="settings-section">
            <ha-entity-picker
              .hass=${this.hass}
              .value=${this._weatherEntity}
              .includeDomains=${["weather"]}
              .label=${n("settings.weather_entity",e)}
              allow-custom-entity
              @value-changed=${this._onWeatherEntityChanged}
            ></ha-entity-picker>
            <span class="field-hint">${n("settings.weather_entity_hint",e)}</span>
          </div>
        </div>
      </ha-card>

      <!-- Card: Mold Risk -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:water-alert"></ha-icon>
            <span>${n("mold.title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <!-- Detection section -->
          <div class="settings-section first">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:bell-alert" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${n("mold.detection",e)}
                </span>
                <span class="toggle-hint">${n("mold.detection_desc",e)}</span>
              </div>
              <ha-switch
                .checked=${this._moldDetectionEnabled}
                @change=${this._onMoldDetectionToggled}
              ></ha-switch>
            </div>
            ${this._moldDetectionEnabled?l`
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldHumidityThreshold)}
                        .label=${n("mold.threshold",e)}
                        .suffix=${"%"}
                        type="number"
                        step="1"
                        min="50"
                        max="90"
                        @change=${this._onMoldThresholdChanged}
                      ></ha-textfield>
                      <span class="field-hint">${n("mold.threshold_hint",e)}</span>
                    </div>
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldSustainedMinutes)}
                        .label=${n("mold.sustained",e)}
                        .suffix=${"min"}
                        type="number"
                        step="5"
                        min="5"
                        max="120"
                        @change=${this._onMoldSustainedChanged}
                      ></ha-textfield>
                      <span class="field-hint">${n("mold.sustained_hint",e)}</span>
                    </div>
                  </div>
                  <div class="threshold-grid" style="margin-top: 12px">
                    <div class="threshold-field">
                      <ha-textfield
                        .value=${String(this._moldNotificationCooldown)}
                        .label=${n("mold.cooldown",e)}
                        .suffix=${"min"}
                        type="number"
                        step="5"
                        min="10"
                        max="1440"
                        @change=${this._onMoldCooldownChanged}
                      ></ha-textfield>
                      <span class="field-hint">${n("mold.cooldown_hint",e)}</span>
                    </div>
                  </div>
                `:h}
          </div>

          <!-- Prevention section -->
          <div class="settings-section">
            <div class="toggle-row">
              <div class="toggle-text">
                <span class="toggle-label">
                  <ha-icon icon="mdi:shield-check" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                  ${n("mold.prevention",e)}
                </span>
                <span class="toggle-hint">${n("mold.prevention_desc",e)}</span>
              </div>
              <ha-switch
                .checked=${this._moldPreventionEnabled}
                @change=${this._onMoldPreventionToggled}
              ></ha-switch>
            </div>
            ${this._moldPreventionEnabled?l`
                  <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 4px;">
                    <ha-select
                      style="width: 100%;"
                      .value=${this._moldPreventionIntensity}
                      .label=${n("mold.intensity",e)}
                      @selected=${this._onMoldIntensityChanged}
                      @closed=${d=>d.stopPropagation()}
                    >
                      <mwc-list-item value="light">${n("mold.intensity_light",e,{delta:"1",unit:C(this.useImperial)})}</mwc-list-item>
                      <mwc-list-item value="medium">${n("mold.intensity_medium",e,{delta:"2",unit:C(this.useImperial)})}</mwc-list-item>
                      <mwc-list-item value="strong">${n("mold.intensity_strong",e,{delta:"3",unit:C(this.useImperial)})}</mwc-list-item>
                    </ha-select>
                    <span class="field-hint">${n("mold.intensity_hint",e)}</span>
                  </div>
                `:h}
          </div>

          <!-- Notifications section (visible when detection OR prevention active) -->
          ${this._moldDetectionEnabled||this._moldPreventionEnabled?l`
                <div class="settings-section">
                  <div class="toggle-row">
                    <div class="toggle-text">
                      <span class="toggle-label">
                        <ha-icon icon="mdi:bell-outline" style="--mdc-icon-size: 18px; vertical-align: middle; margin-right: 4px"></ha-icon>
                        ${n("mold.notifications_enabled",e)}
                      </span>
                      <span class="toggle-hint">${n("mold.notifications_enabled_hint",e)}</span>
                    </div>
                    <ha-switch
                      .checked=${this._moldNotificationsEnabled}
                      @change=${this._onMoldNotificationsEnabledToggled}
                    ></ha-switch>
                  </div>
                  ${this._moldNotificationsEnabled?l`
                  <p class="hint" style="margin-top: 12px">${n("mold.notifications_desc",e)}</p>

                  <!-- Target list -->
                  <div class="presence-person-list">
                    ${this._moldNotificationTargets.map((d,g)=>{var v,y;const m=d.entity_id?((y=(v=this.hass.states[d.entity_id])==null?void 0:v.attributes)==null?void 0:y.friendly_name)??d.entity_id.replace("notify.",""):n("mold.target_unnamed",e);return l`
                        <div class="mold-target-card">
                          <div class="mold-target-header">
                            <ha-icon icon="mdi:bell" style="--mdc-icon-size: 18px; color: var(--secondary-text-color)"></ha-icon>
                            <span>${m}</span>
                            <ha-icon-button
                              .path=${"M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"}
                              @click=${()=>this._removeMoldTarget(g)}
                            ></ha-icon-button>
                          </div>
                          <div class="mold-target-detail">
                            <ha-entity-picker
                              .hass=${this.hass}
                              .value=${d.person_entity}
                              .includeDomains=${["person"]}
                              .label=${n("mold.target_person",e)}
                              allow-custom-entity
                              @value-changed=${E=>this._onMoldTargetPersonChanged(g,E)}
                            ></ha-entity-picker>
                            <ha-select
                              .value=${d.notify_when}
                              @selected=${E=>this._onMoldTargetWhenChanged(g,E)}
                              @closed=${E=>E.stopPropagation()}
                            >
                              <mwc-list-item value="always">${n("mold.target_when_always",e)}</mwc-list-item>
                              <mwc-list-item value="home_only">${n("mold.target_when_home",e)}</mwc-list-item>
                            </ha-select>
                          </div>
                        </div>
                      `})}
                  </div>

                  <!-- Add target picker -->
                  <div style="margin-top: 8px">
                    <ha-entity-picker
                      .hass=${this.hass}
                      .value=${""}
                      .includeDomains=${["notify"]}
                      .label=${n("mold.add_target_label",e)}
                      allow-custom-entity
                      @value-changed=${this._onMoldTargetAdded}
                    ></ha-entity-picker>
                    <span class="field-hint">${n("mold.add_target_hint",e)}</span>
                  </div>

                  <!-- Prevention notify toggle -->
                  ${this._moldPreventionEnabled?l`
                        <div class="toggle-row" style="margin-top: 12px">
                          <div class="toggle-text">
                            <span class="toggle-label">${n("mold.prevention_notify",e)}</span>
                            <span class="toggle-hint">${n("mold.prevention_notify_hint",e)}</span>
                          </div>
                          <ha-switch
                            .checked=${this._moldPreventionNotify}
                            @change=${this._onMoldPreventionNotifyToggled}
                          ></ha-switch>
                        </div>
                      `:h}
                    `:h}
                </div>
              `:h}
        </div>
      </ha-card>

      <!-- Card: Reset Thermal Data -->
      <ha-card>
        <div class="card-header">
          <div class="header-title">
            <ha-icon icon="mdi:restart"></ha-icon>
            <span>${n("settings.reset_title",e)}</span>
          </div>
        </div>
        <div class="card-content">
          <p class="hint">${n("settings.reset_hint",e)}</p>

          <div class="settings-section first">
            <div class="reset-row">
              <div class="reset-text">
                <span class="toggle-label">${n("settings.reset_all_label",e)}</span>
                <span class="toggle-hint">${n("settings.reset_all_hint",e)}</span>
              </div>
              <button class="reset-btn" @click=${this._resetAllModels}>
                <ha-icon icon="mdi:restart-alert"></ha-icon>
                ${n("settings.reset_all_btn",e)}
              </button>
            </div>
          </div>

          <div class="settings-section">
            <div class="reset-text" style="margin-bottom: 12px">
              <span class="toggle-label">${n("settings.reset_room_label",e)}</span>
              <span class="toggle-hint">${n("settings.reset_room_hint",e)}</span>
            </div>
            ${s.length>0?l`
                  <div class="reset-room-row">
                    <ha-select
                      .value=${this._resetSelectedRoom}
                      .label=${n("settings.reset_room_select",e)}
                      @selected=${this._onResetRoomSelected}
                      @closed=${d=>d.stopPropagation()}
                    >
                      ${s.map(d=>l`<mwc-list-item .value=${d.areaId}>${d.name}</mwc-list-item>`)}
                    </ha-select>
                    <button
                      class="reset-btn"
                      ?disabled=${!this._resetSelectedRoom}
                      @click=${()=>this._resetSelectedRoom&&this._resetRoomModel(this._resetSelectedRoom)}
                    >
                      <ha-icon icon="mdi:restart"></ha-icon>
                      ${n("settings.reset_btn",e)}
                    </button>
                  </div>
                `:l`<p class="hint">${n("settings.reset_no_rooms",e)}</p>`}
          </div>
        </div>
      </ha-card>
      </div>
    `}_getSensorValue(e){const t=this.hass.states[e];if(!t||t.state==="unavailable"||t.state==="unknown")return null;const i=parseFloat(t.state);return isNaN(i)?null:Math.round(i*10)/10}_tsToDatetimeLocal(e){const t=new Date(e*1e3),i=s=>String(s).padStart(2,"0");return`${t.getFullYear()}-${i(t.getMonth()+1)}-${i(t.getDate())}T${i(t.getHours())}:${i(t.getMinutes())}`}_onVacationToggled(e){this._vacationActive=e.target.checked,this._vacationActive||(this._vacationUntil=""),this._autoSave()}_onVacationUntilChanged(e){this._vacationUntil=e.target.value,this._autoSave()}_onVacationTempChanged(e){const t=parseFloat(e.target.value);isNaN(t)||(this._vacationTemp=t,this._autoSave())}_onPresenceToggled(e){this._presenceEnabled=e.target.checked,this._autoSave()}_onValveProtectionToggled(e){this._valveProtectionEnabled=e.target.checked,this._autoSave()}_onValveProtectionIntervalChanged(e){const t=parseInt(e.target.value,10);!isNaN(t)&&t>=1&&t<=90&&t!==this._valveProtectionInterval&&(this._valveProtectionInterval=t,this._autoSave())}_onLearningToggled(e){e.target.checked?this._learningDisabledRooms=[]:(this._learningDisabledRooms=Object.keys(this.rooms),this._showLearningExceptions=!1),this._autoSave()}_toggleLearningExceptions(){this._showLearningExceptions=!this._showLearningExceptions}_setControlMode(e){this._controlMode!==e&&(this._controlMode=e,this._autoSave())}_onClimateControlChanged(e){this._climateControlActive=e.target.checked,this._autoSave()}_onLearningRoomToggled(e,t){const i=new Set(this._learningDisabledRooms);t?i.add(e):i.delete(e),this._learningDisabledRooms=[...i],this._autoSave()}_onOutdoorTempChanged(e){var i;const t=((i=e.detail)==null?void 0:i.value)??"";t!==this._outdoorTempSensor&&(this._outdoorTempSensor=t,this._autoSave())}_onOutdoorHumidityChanged(e){var i;const t=((i=e.detail)==null?void 0:i.value)??"";t!==this._outdoorHumiditySensor&&(this._outdoorHumiditySensor=t,this._autoSave())}_onOutdoorCoolingMinChanged(e){const t=parseFloat(e.target.value);isNaN(t)||t!==this._outdoorCoolingMin&&(this._outdoorCoolingMin=t,this._autoSave())}_onOutdoorHeatingMaxChanged(e){const t=parseFloat(e.target.value);isNaN(t)||t!==this._outdoorHeatingMax&&(this._outdoorHeatingMax=t,this._autoSave())}_onComfortWeightChanged(e){const t=parseInt(e.target.value,10);!isNaN(t)&&t!==this._comfortWeight&&(this._comfortWeight=t,this._autoSave())}_onWeatherEntityChanged(e){var i;const t=((i=e.detail)==null?void 0:i.value)??"";t!==this._weatherEntity&&(this._weatherEntity=t,this._autoSave())}_onPredictionEnabledChanged(e){this._predictionEnabled=e.target.checked,this._autoSave()}_onResetRoomSelected(e){const t=e.target;this._resetSelectedRoom=t.value??""}async _resetRoomModel(e){const t=this.hass.language;if(confirm(n("settings.reset_room_confirm",t)))try{L(this,"saving"),await this.hass.callWS({type:"roommind/thermal/reset",area_id:e}),L(this,"saved")}catch{L(this,"error")}}async _resetAllModels(){const e=this.hass.language;if(confirm(n("settings.reset_all_confirm",e)))try{L(this,"saving"),await this.hass.callWS({type:"roommind/thermal/reset_all"}),L(this,"saved")}catch{L(this,"error")}}_removeMoldTarget(e){this._moldNotificationTargets=this._moldNotificationTargets.filter((t,i)=>i!==e),this._autoSave()}_onMoldTargetAdded(e){var s;const t=((s=e.detail)==null?void 0:s.value)??"";if(!t)return;this._moldNotificationTargets=[...this._moldNotificationTargets,{entity_id:t,person_entity:"",notify_when:"always"}];const i=e.target;i&&(i.value=""),this._autoSave()}_onMoldTargetPersonChanged(e,t){var o;const i=((o=t.detail)==null?void 0:o.value)??"",s=[...this._moldNotificationTargets];s[e]={...s[e],person_entity:i},this._moldNotificationTargets=s,this._autoSave()}_onMoldTargetWhenChanged(e,t){const i=t.target.value;if(!i)return;const s=[...this._moldNotificationTargets];s[e]={...s[e],notify_when:i},this._moldNotificationTargets=s,this._autoSave()}_onMoldNotificationsEnabledToggled(e){this._moldNotificationsEnabled=e.target.checked,this._autoSave()}_onMoldDetectionToggled(e){this._moldDetectionEnabled=e.target.checked,this._autoSave()}_onMoldThresholdChanged(e){const t=parseFloat(e.target.value);!isNaN(t)&&t>=50&&t<=90&&t!==this._moldHumidityThreshold&&(this._moldHumidityThreshold=t,this._autoSave())}_onMoldSustainedChanged(e){const t=parseInt(e.target.value,10);!isNaN(t)&&t>=5&&t<=120&&t!==this._moldSustainedMinutes&&(this._moldSustainedMinutes=t,this._autoSave())}_onMoldCooldownChanged(e){const t=parseInt(e.target.value,10);!isNaN(t)&&t>=10&&t<=1440&&t!==this._moldNotificationCooldown&&(this._moldNotificationCooldown=t,this._autoSave())}_onMoldPreventionToggled(e){this._moldPreventionEnabled=e.target.checked,this._autoSave()}_onMoldIntensityChanged(e){const t=e.target.value;t&&t!==this._moldPreventionIntensity&&(this._moldPreventionIntensity=t,this._autoSave())}_onMoldPreventionNotifyToggled(e){this._moldPreventionNotify=e.target.checked,this._autoSave()}_autoSave(){this._saveDebounce&&clearTimeout(this._saveDebounce),this._saveDebounce=setTimeout(()=>this._doSave(),500)}async _doSave(){L(this,"saving");try{await this.hass.callWS({type:"roommind/settings/save",climate_control_active:this._climateControlActive,learning_disabled_rooms:this._learningDisabledRooms,outdoor_temp_sensor:this._outdoorTempSensor,outdoor_humidity_sensor:this._outdoorHumiditySensor,outdoor_cooling_min:this._outdoorCoolingMin,outdoor_heating_max:this._outdoorHeatingMax,control_mode:this._controlMode,comfort_weight:this._comfortWeight,weather_entity:this._weatherEntity,prediction_enabled:this._predictionEnabled,vacation_temp:this._vacationTemp,vacation_until:this._vacationActive&&this._vacationUntil?new Date(this._vacationUntil).getTime()/1e3:null,presence_enabled:this._presenceEnabled,presence_persons:this._presencePersons.filter(e=>e),valve_protection_enabled:this._valveProtectionEnabled,valve_protection_interval_days:this._valveProtectionInterval,mold_detection_enabled:this._moldDetectionEnabled,mold_humidity_threshold:this._moldHumidityThreshold,mold_sustained_minutes:this._moldSustainedMinutes,mold_notification_cooldown:this._moldNotificationCooldown,mold_notifications_enabled:this._moldNotificationsEnabled,mold_notification_targets:this._moldNotificationTargets.filter(e=>e.entity_id),mold_prevention_enabled:this._moldPreventionEnabled,mold_prevention_intensity:this._moldPreventionIntensity,mold_prevention_notify_enabled:this._moldPreventionNotify,mold_prevention_notify_targets:this._moldPreventionNotify?this._moldNotificationTargets.filter(e=>e.entity_id):[]}),L(this,"saved")}catch{L(this,"error")}}};b.styles=O`
    :host {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      align-items: start;
    }

    .left-column,
    .right-column {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 0;
      font-size: 16px;
      font-weight: 500;
    }

    .header-title {
      display: flex;
      align-items: center;
      gap: 8px;
      --mdc-icon-size: 20px;
    }

    .card-content {
      padding: 8px 16px 16px;
    }

    .settings-section {
      padding: 16px 0;
      border-top: 1px solid var(--divider-color);
    }

    .settings-section:first-child,
    .settings-section.first {
      border-top: none;
    }

    .toggle-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }

    .toggle-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .toggle-label {
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .toggle-hint {
      font-size: 13px;
      color: var(--secondary-text-color);
      line-height: 1.4;
    }

    .exceptions-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px 0 0;
      margin: 0;
      cursor: pointer;
      font-size: 13px;
      color: var(--primary-color);
      font-family: inherit;
    }

    .exceptions-link:hover {
      text-decoration: underline;
    }

    .presence-person-list {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .presence-person-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 8px 4px 12px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.04);
    }

    .presence-person-name {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }

    .room-toggles {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 12px;
    }

    .room-toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 0;
    }

    .room-toggle-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .sensor-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .current-value {
      margin-top: 8px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .current-value.muted {
      color: var(--secondary-text-color);
    }

    .loading {
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .hint {
      color: var(--secondary-text-color);
      font-size: 13px;
      margin: 0 0 12px;
    }

    .section-label {
      display: block;
      margin-bottom: 8px;
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .threshold-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .threshold-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .threshold-field ha-textfield {
      width: 100%;
    }

    .field-hint {
      color: var(--secondary-text-color);
      font-size: 12px;
    }

    .radio-group {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .radio-option {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
    }

    .slider-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .slider-row input[type="range"] {
      flex: 1;
      accent-color: var(--primary-color);
    }

    .slider-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .reset-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }

    .reset-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .reset-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border: 1px solid var(--error-color, #d32f2f);
      border-radius: 8px;
      background: transparent;
      color: var(--error-color, #d32f2f);
      font-size: 13px;
      font-family: inherit;
      cursor: pointer;
      transition: background 0.15s;
      --mdc-icon-size: 16px;
      white-space: nowrap;
    }

    .reset-btn:hover {
      background: rgba(211, 47, 47, 0.08);
    }

    .reset-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .reset-btn:disabled:hover {
      background: transparent;
    }

    .reset-room-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .reset-room-row ha-select {
      flex: 1;
    }

    .mold-target-card {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 8px 8px 8px 12px;
      border-radius: 8px;
      background: rgba(0, 0, 0, 0.04);
    }

    .mold-target-header {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .mold-target-header span {
      flex: 1;
      font-size: 14px;
      font-weight: 500;
    }

    .mold-target-detail {
      display: flex;
      gap: 8px;
      align-items: center;
      padding-left: 26px;
    }

    .mold-target-detail ha-entity-picker {
      flex: 1;
    }

    .mold-target-detail ha-select {
      min-width: 120px;
    }

    @media (max-width: 600px) {
      :host {
        grid-template-columns: 1fr;
      }

      .sensor-grid,
      .threshold-grid {
        grid-template-columns: 1fr;
      }

      .mold-target-detail {
        flex-direction: column;
        padding-left: 0;
      }

      .reset-row {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
      }
    }
  `,x([_({attribute:!1})],b.prototype,"hass",2),x([_({attribute:!1})],b.prototype,"rooms",2),x([_({type:Boolean})],b.prototype,"useImperial",2),x([u()],b.prototype,"_climateControlActive",2),x([u()],b.prototype,"_learningDisabledRooms",2),x([u()],b.prototype,"_showLearningExceptions",2),x([u()],b.prototype,"_outdoorTempSensor",2),x([u()],b.prototype,"_outdoorHumiditySensor",2),x([u()],b.prototype,"_outdoorCoolingMin",2),x([u()],b.prototype,"_outdoorHeatingMax",2),x([u()],b.prototype,"_controlMode",2),x([u()],b.prototype,"_comfortWeight",2),x([u()],b.prototype,"_weatherEntity",2),x([u()],b.prototype,"_predictionEnabled",2),x([u()],b.prototype,"_vacationActive",2),x([u()],b.prototype,"_vacationTemp",2),x([u()],b.prototype,"_vacationUntil",2),x([u()],b.prototype,"_presenceEnabled",2),x([u()],b.prototype,"_presencePersons",2),x([u()],b.prototype,"_valveProtectionEnabled",2),x([u()],b.prototype,"_valveProtectionInterval",2),x([u()],b.prototype,"_moldDetectionEnabled",2),x([u()],b.prototype,"_moldHumidityThreshold",2),x([u()],b.prototype,"_moldSustainedMinutes",2),x([u()],b.prototype,"_moldNotificationCooldown",2),x([u()],b.prototype,"_moldNotificationsEnabled",2),x([u()],b.prototype,"_moldNotificationTargets",2),x([u()],b.prototype,"_moldPreventionEnabled",2),x([u()],b.prototype,"_moldPreventionIntensity",2),x([u()],b.prototype,"_moldPreventionNotify",2),x([u()],b.prototype,"_resetSelectedRoom",2),x([u()],b.prototype,"_loaded",2),b=x([U("rs-settings")],b);var ei=Object.defineProperty,ti=Object.getOwnPropertyDescriptor,P=(e,t,i,s)=>{for(var o=s>1?void 0:s?ti(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&ei(t,i,o),o};const ii=3*36e5;let D=class extends I{constructor(){super(...arguments),this.rooms={},this.initialRoom="",this.controlMode="bangbang",this.useImperial=!1,this._selectedRoom="",this._rangeStart=new Date(new Date().setHours(0,0,0,0)).getTime(),this._rangeEnd=Date.now(),this._data=null,this._chartAnchor=Date.now(),this._loading=!1,this._hiddenSeries=new Set(["outdoor_temp"]),this._expandedStat=null,this._chartInfoExpanded=!1,this._openDropdown=null,this._activeQuick="24h",this._boundCloseDropdowns=this._closeDropdowns.bind(this)}connectedCallback(){super.connectedCallback(),this._refreshInterval=setInterval(()=>this._silentRefresh(),6e4),document.addEventListener("click",this._boundCloseDropdowns)}disconnectedCallback(){super.disconnectedCallback(),this._refreshInterval&&(clearInterval(this._refreshInterval),this._refreshInterval=void 0),document.removeEventListener("click",this._boundCloseDropdowns)}willUpdate(e){e.has("initialRoom")&&this.initialRoom&&(this._selectedRoom=this.initialRoom);let t=!1;if(e.has("rooms")&&!this._selectedRoom){const i=Object.keys(this.rooms);i.length>0&&(this._selectedRoom=i[0],t=!0,this.dispatchEvent(new CustomEvent("room-selected",{detail:{areaId:i[0]},bubbles:!0,composed:!0})))}(t||e.has("_selectedRoom")||e.has("_rangeStart")||e.has("_rangeEnd"))&&this._selectedRoom&&this._fetchData()}updated(e){(e.has("rooms")||e.has("_selectedRoom"))&&this._selectedRoom&&this.updateComplete.then(()=>{var i;const t=(i=this.renderRoot)==null?void 0:i.querySelector("ha-select");t&&t.value!==this._selectedRoom&&(t.value=this._selectedRoom)})}render(){const e=this.hass.language,t=this._getConfiguredRooms();return l`
      ${this._renderRoomSelector(t,e)}
      ${this._selectedRoom?l`
            ${this._renderRangeButtons(e)}
            ${this._loading?l`<div class="loading">${n("panel.loading",e)}</div>`:l`
                  ${this._renderChart(e)}
                  ${this._renderModelStatus(e)}
                `}
          `:l`
            <div class="no-data">
              <ha-icon icon="mdi:chart-line" style="--mdc-icon-size: 48px; opacity: 0.4"></ha-icon>
              <p>${n("analytics.select_room",e)}</p>
            </div>
          `}
    `}_getConfiguredRooms(){return Object.entries(this.rooms).map(([e,t])=>{var s,o;const i=(o=(s=this.hass)==null?void 0:s.areas)==null?void 0:o[e];return{area_id:e,name:t.display_name||(i==null?void 0:i.name)||e}})}_renderRoomSelector(e,t){return l`
      <div class="selector-row">
        <ha-select
          .value=${this._selectedRoom}
          .label=${n("analytics.select_room",t)}
          naturalMenuWidth
          fixedMenuPosition
          @selected=${this._onRoomSelected}
          @closed=${i=>i.stopPropagation()}
        >
          ${e.map(i=>l`
              <ha-list-item .value=${i.area_id}>${i.name}</ha-list-item>
            `)}
        </ha-select>
      </div>
    `}_renderRangeButtons(e){const t=[{key:"24h",label:n("analytics.range_1d",e),days:1},{key:"2d",label:n("analytics.range_2d",e),days:2},{key:"7d",label:n("analytics.range_7d",e),days:7},{key:"30d",label:n("analytics.range_30d",e),days:30}],i=this._data&&(this._data.history.length>0||this._data.detail.length>0),s=o=>new Date(o).toLocaleString(this.hass.language,{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});return l`
      <div class="range-row">
        <div class="range-controls">
          <div class="range-bar">
            ${t.map(o=>l`
                <button
                  class="range-chip"
                  ?active=${this._activeQuick===o.key}
                  @click=${()=>this._onQuickRange(o.key,o.days)}
                >
                  ${o.label}
                </button>
              `)}
            <div class="range-chip picker-chip ${this._activeQuick===null?"picker-active":""}">
              <ha-date-range-picker
                .hass=${this.hass}
                .startDate=${new Date(this._rangeStart)}
                .endDate=${new Date(this._rangeEnd)}
                .ranges=${!1}
                time-picker
                auto-apply
                minimal
                @value-changed=${this._onDateRangeChanged}
              ></ha-date-range-picker>
            </div>
          </div>
          <span class="date-label ${this._activeQuick===null?"custom-active":""}">${s(this._rangeStart)} – ${s(this._rangeEnd)}</span>
        </div>
        <div class="action-buttons">
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!i}
              @click=${o=>{o.stopPropagation(),this._toggleDropdown("csv")}}
            >
              <ha-icon icon="mdi:download"></ha-icon>
              ${n("analytics.export",e)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown==="csv"?l`<div class="export-dropdown" @click=${o=>o.stopPropagation()}>
                  <button @click=${this._exportCsv}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${n("analytics.export_download",e)}
                  </button>
                  <button @click=${this._copyCsvToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${n("analytics.export_clipboard",e)}
                  </button>
                </div>`:h}
          </div>
          <div class="export-split">
            <button
              class="export-btn"
              ?disabled=${!this._selectedRoom||!this._data}
              @click=${o=>{o.stopPropagation(),this._toggleDropdown("diag")}}
            >
              <ha-icon icon="mdi:bug-outline"></ha-icon>
              ${n("analytics.copy_diagnostics",e)}
              <ha-icon class="arrow-icon" icon="mdi:chevron-down"></ha-icon>
            </button>
            ${this._openDropdown==="diag"?l`<div class="export-dropdown" @click=${o=>o.stopPropagation()}>
                  <button @click=${this._exportDiagnostics}>
                    <ha-icon icon="mdi:download"></ha-icon>
                    ${n("analytics.export_download",e)}
                  </button>
                  <button @click=${this._copyDiagnosticsToClipboard}>
                    <ha-icon icon="mdi:content-copy"></ha-icon>
                    ${n("analytics.export_clipboard",e)}
                  </button>
                </div>`:h}
          </div>
        </div>
      </div>
    `}_renderChart(e){var p;const t=this._data?[...this._data.history,...this._data.detail]:[],i=[...t,...((p=this._data)==null?void 0:p.forecast)??[]],s=t.length>0?this._buildChartSeries(t,e):[],o=[],a=s.map(c=>{const d=c.id,g=c.lineStyle||{},m=d.endsWith("_events");if(this._hiddenSeries.has(d)){const y={...c,lineStyle:{...g,width:0,opacity:0}};return c.areaStyle&&(y.areaStyle={...c.areaStyle,opacity:0}),y}if(!m&&d!=="now_marker")for(const y of c.data)y&&y[1]!=null&&o.push(y[1]);const v={...c,lineStyle:{...g,opacity:1}};return c.areaStyle&&(v.areaStyle={...c.areaStyle,opacity:1}),v}),r=this._buildChartOptions(o,e,i);return l`
      <ha-card>
        <div class="card-header">
          <span>${n("analytics.temperature",e)}</span>
          <ha-icon
            class="info-icon chart-info-toggle ${this._chartInfoExpanded?"info-active":""}"
            icon="mdi:information-outline"
            @click=${()=>{this._chartInfoExpanded=!this._chartInfoExpanded}}
          ></ha-icon>
        </div>
        ${this._chartInfoExpanded?l`<div class="chart-info-panel">
              ${this._renderMarkdown(n("analytics.chart_info_body",e))}
            </div>`:h}
        ${t.length>0?l`
              <ha-chart-base
                .hass=${this.hass}
                .data=${a}
                .options=${r}
                .height=${"300px"}
                style="height: 300px"
              ></ha-chart-base>
              ${this._renderSeriesLegend(s)}
            `:l`<div class="chart-empty">
              <ha-icon icon="mdi:chart-line"></ha-icon>
              <span>${n("analytics.no_data",e)}</span>
            </div>`}
      </ha-card>
    `}_buildChartSeries(e,t){var E;const i=[],s=[],o=[],a=[];for(const k of e){const $=k.ts*1e3;k.room_temp!==null&&i.push([$,k.room_temp]),k.target_temp!==null&&s.push([$,k.target_temp]),k.predicted_temp!==null&&o.push([$,k.predicted_temp]),k.outdoor_temp!==null&&a.push([$,k.outdoor_temp])}for(const k of((E=this._data)==null?void 0:E.forecast)??[]){const $=k.ts*1e3;k.target_temp!==null&&s.push([$,k.target_temp]),k.predicted_temp!==null&&o.push([$,k.predicted_temp])}const r=[{id:"room_temp",type:"line",name:n("analytics.temperature",t),color:"rgb(255, 152, 0)",data:i,showSymbol:!1,smooth:!0,lineStyle:{width:2},yAxisIndex:0},{id:"target_temp",type:"line",name:n("analytics.target",t),color:"rgb(76, 175, 80)",data:s,showSymbol:!1,smooth:!1,lineStyle:{width:2,type:"dashed"},yAxisIndex:0}];o.length>0&&r.push({id:"predicted_temp",type:"line",name:n("analytics.prediction",t),color:"rgb(33, 150, 243)",data:o,showSymbol:!1,smooth:!0,lineStyle:{width:2,type:"dotted"},yAxisIndex:0}),a.length>0&&r.push({id:"outdoor_temp",type:"line",name:n("analytics.outdoor",t),color:"rgb(158, 158, 158)",data:a,showSymbol:!1,smooth:!0,lineStyle:{width:1},yAxisIndex:0});const p=[],c=[],d=[];let g=!1,m=!1,v=!1;for(const k of e){const $=k.ts*1e3;k.mode==="heating"?(p.push([$,999]),g=!0):p.push([$,null]),k.mode==="cooling"?(c.push([$,999]),m=!0):c.push([$,null]),k.window_open?(d.push([$,999]),v=!0):d.push([$,null])}g&&r.push({id:"heating_events",type:"line",name:n("analytics.heating_period",t),color:"rgb(244, 67, 54)",data:p,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(244, 67, 54, 0.08)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1}),m&&r.push({id:"cooling_events",type:"line",name:n("analytics.cooling_period",t),color:"rgb(63, 81, 181)",data:c,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(63, 81, 181, 0.08)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1}),v&&r.push({id:"window_events",type:"line",name:n("analytics.window_open_period",t),color:"rgb(0, 150, 136)",data:d,showSymbol:!1,lineStyle:{width:0},areaStyle:{color:"rgba(0, 150, 136, 0.1)",origin:"start"},tooltip:{show:!1},yAxisIndex:0,z:-1,connectNulls:!1});const y=this._chartAnchor;return r.push({id:"now_marker",type:"line",name:"",color:"rgba(255,255,255,0.3)",data:[[y,-999],[y,999]],showSymbol:!1,lineStyle:{width:1,type:"dashed"},yAxisIndex:0,tooltip:{show:!1},z:-2}),r}_buildChartOptions(e,t,i=[]){const s=C(this.useImperial),o={type:"value",name:s};if(e.length>0){let c=1/0,d=-1/0;for(const v of e)v<c&&(c=v),v>d&&(d=v);const g=d-c,m=Math.max(g*.1,.5);o.min=Math.floor((c-m)*2)/2,o.max=Math.ceil((d+m)*2)/2}const a=this._chartAnchor,r=this._rangeStart,p=Math.abs(this._rangeEnd-Date.now())<36e5;return{xAxis:{type:"time",min:r,max:p?a+ii:this._rangeEnd},yAxis:o,dataZoom:[{type:"inside",xAxisIndex:0,filterMode:"none"}],tooltip:{trigger:"axis",axisPointer:{snap:!1},valueFormatter:c=>c.toFixed(1)+" "+s,formatter:c=>{var E,k;if(!Array.isArray(c)||c.length===0)return"";let m=`<div style="font-weight:500;margin-bottom:4px">${new Date(c[0].value[0]).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</div>`,v=null,y=null;for(const $ of c){if((E=$.seriesId)!=null&&E.endsWith("_events"))continue;const M=(k=$.value)==null?void 0:k[1];M!=null&&(m+=`<div>${$.color?`<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${$.color};margin-right:6px"></span>`:""}${$.seriesName}: ${M.toFixed(1)} ${s}</div>`,$.seriesId==="room_temp"&&(v=M),$.seriesId==="predicted_temp"&&(y=M))}if(v!==null&&y!==null){const $=v-y,M=$>=0?"+":"";m+=`<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px">Delta: ${M}${$.toFixed(2)} ${s}</div>`}if(i.length>0){const $=c[0].value[0]/1e3;let M=null,J=1/0;for(const f of i){const T=Math.abs(f.ts-$);T<J&&(J=T,M=f)}if(M){const f=[];if(M.mode==="heating"){const T=M.heating_power;if(T!=null&&T>0&&T<100?f.push(`${n("analytics.heating_period",t)} ${T}%`):f.push(n("analytics.heating_period",t)),T!=null&&T>0&&M.room_temp!=null){const R=Math.round((M.room_temp+T/100*(30-M.room_temp))*10)/10;f.push(`TRV ${R.toFixed(1)} ${s}`)}}else M.mode==="cooling"&&f.push(n("analytics.cooling_period",t));M.window_open&&f.push(n("analytics.window_open_period",t)),f.length>0&&(m+=`<div style="border-top:1px solid rgba(128,128,128,0.3);margin-top:4px;padding-top:4px;color:rgba(255,255,255,0.7)">${f.join(" · ")}</div>`)}}return m}},grid:{top:15,left:10,right:10,bottom:5,containLabel:!0}}}_renderModelStatus(e){var tt,it,st;const t=!!((it=(tt=this._data)==null?void 0:tt.model)!=null&&it.model),i=(st=this._data)==null?void 0:st.model,s=i==null?void 0:i.model,o=(i==null?void 0:i.confidence)??0,a=(i==null?void 0:i.n_samples)??0,r=(i==null?void 0:i.n_heating)??0,p=(i==null?void 0:i.n_cooling)??0,c=(i==null?void 0:i.applicable_modes)??[],d=i==null?void 0:i.prediction_std_idle,g=i==null?void 0:i.prediction_std_heating,m=(i==null?void 0:i.mpc_active)??!1,v=Math.round(o*100),y=new Set(c),E=y.has("heating"),k=y.has("cooling"),$=r>=10,M=p>=10,J=a-r-p>=10,f=(i==null?void 0:i.n_observations)??a,T="—",R=[],re=(Z,ot,nt,pi,ci)=>{R.push({id:Z,labelKey:nt,infoKey:ci});const at=this._expandedStat===Z;return l`
        <div class="model-stat ${at?"active":""}" @click=${()=>this._toggleStat(Z)}>
          <div class="stat-content">
            <span class="model-value ${ot===T?"pending":""}">${ot}</span>
            <span class="model-label">${n(nt,e)}${""}</span>
          </div>
          <ha-icon
            class="info-icon ${at?"info-active":""}"
            icon="mdi:information-outline"
          ></ha-icon>
        </div>
      `};return l`
      <ha-card>
        <div class="card-header">
          <span>${n("analytics.model_status",e)}</span>
        </div>
        <div class="card-content">
          <!-- Confidence hero -->
          <div class="confidence-hero">
            <div class="confidence-top">
              <div class="confidence-main">
                <span class="confidence-value">${t?v+"%":"0%"}</span>
                <span class="confidence-label">
                  ${n("analytics.confidence",e)}
                  <ha-icon
                    class="info-icon ${this._expandedStat==="confidence"?"info-active":""}"
                    icon="mdi:information-outline"
                    @click=${()=>this._toggleStat("confidence")}
                  ></ha-icon>
                </span>
              </div>
              <div class="confidence-meta">
                <span class="meta-value">${t?f:0}</span>
                <span class="meta-label">
                  ${n("analytics.data_points",e)}
                  <ha-icon
                    class="info-icon ${this._expandedStat==="data_points"?"info-active":""}"
                    icon="mdi:information-outline"
                    @click=${()=>this._toggleStat("data_points")}
                  ></ha-icon>
                </span>
              </div>
            </div>
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${t?v:0}%"></div>
            </div>
            <div class="control-mode-badge ${m?"mpc":"bangbang"}">
              <ha-icon icon=${m?"mdi:brain":"mdi:school-outline"}></ha-icon>
              ${n(m?"analytics.control_mode_mpc":"analytics.control_mode_bangbang",e)}
            </div>
            ${this._expandedStat==="confidence"?l`<div class="info-panel stat-info-panel">
                  <strong>${n("analytics.confidence",e)}</strong>
                  ${n("analytics.info.confidence",e)}
                </div>`:h}
            ${this._expandedStat==="data_points"?l`<div class="info-panel stat-info-panel">
                  <strong>${n("analytics.data_points",e)}</strong>
                  ${n("analytics.info.data_points",e)}
                </div>`:h}
          </div>

          <!-- Stats grid -->
          <div class="model-grid">
            ${re("time_constant",J&&s&&s.U>0?(1/s.U).toFixed(1)+"h":T,"analytics.time_constant","","analytics.info.time_constant")}
            ${E?re("heating_rate",$&&s?s.Q_heat.toFixed(1):T,"analytics.heating_rate","","analytics.info.heating_rate"):h}
            ${k?re("cooling_rate",M&&s?s.Q_cool.toFixed(1):T,"analytics.cooling_rate","","analytics.info.cooling_rate"):h}
            ${s&&s.Q_solar>.1?re("solar_gain",s.Q_solar.toFixed(1),"analytics.solar_gain","","analytics.info.solar_gain"):h}
            ${re("accuracy_idle",J&&d!=null?"±"+d.toFixed(2)+C(this.useImperial):T,"analytics.accuracy_idle","","analytics.info.accuracy_idle")}
            ${E?re("accuracy_heating",$&&g!=null?"±"+g.toFixed(2)+C(this.useImperial):T,"analytics.accuracy_heating","","analytics.info.accuracy_heating"):h}
          </div>
          ${this._expandedStat&&R.find(Z=>Z.id===this._expandedStat)?l`<div class="info-panel stat-info-panel">
                <strong>${n(R.find(Z=>Z.id===this._expandedStat).labelKey,e)}</strong>
                ${n(R.find(Z=>Z.id===this._expandedStat).infoKey,e)}
              </div>`:h}

        </div>
      </ha-card>
    `}_renderSeriesLegend(e){const t=e.filter(i=>i.id!=="now_marker");return l`
      <div class="series-legend">
        ${t.map(i=>{const s=i.id,o=this._hiddenSeries.has(s);return l`
            <button
              class="legend-item ${o?"legend-hidden":""}"
              @click=${()=>this._toggleSeries(s)}
            >
              <span class="legend-dot" style="background: ${i.color}"></span>
              ${i.name}
            </button>
          `})}
      </div>
    `}_renderMarkdown(e){return e.split(`

`).map(i=>l`<p>
          ${i.split(/(\*\*.*?\*\*)/).map(s=>s.startsWith("**")&&s.endsWith("**")?l`<strong>${s.slice(2,-2)}</strong>`:s)}
        </p>`)}_toggleStat(e){this._expandedStat=this._expandedStat===e?null:e}_toggleSeries(e){const t=new Set(this._hiddenSeries);t.has(e)?t.delete(e):t.add(e),this._hiddenSeries=t}_onRoomSelected(e){const i=e.target.value??"";i&&i!==this._selectedRoom&&(this._selectedRoom=i,this.dispatchEvent(new CustomEvent("room-selected",{detail:{areaId:i},bubbles:!0,composed:!0})))}_onQuickRange(e,t){const i=new Date,s=new Date(i);s.setDate(s.getDate()-(t-1)),s.setHours(0,0,0,0),this._activeQuick=e,this._rangeEnd=i.getTime(),this._rangeStart=s.getTime(),this._chartAnchor=i.getTime()}_onDateRangeChanged(e){const{startDate:t,endDate:i}=e.detail.value;!t||!i||(this._activeQuick=null,this._rangeStart=t.getTime(),this._rangeEnd=i.getTime(),this._chartAnchor=i.getTime())}_buildCsvString(){if(!this._data)return null;const e=[...this._data.history,...this._data.detail];if(e.length===0)return null;const t="timestamp,datetime,room_temp,outdoor_temp,target_temp,mode,predicted_temp,window_open",i=e.map(s=>{const o=new Date(s.ts*1e3).toISOString(),a=s.room_temp??"",r=s.outdoor_temp??"",p=s.target_temp??"",c=s.predicted_temp??"";return`${s.ts},${o},${a},${r},${p},${s.mode},${c},${s.window_open}`});return[t,...i].join(`
`)}_buildDiagnosticsString(){var o,a,r,p;if(!this._selectedRoom||!this._data)return null;const e=(o=this.rooms)==null?void 0:o[this._selectedRoom],t=[...this._data.history??[],...this._data.detail??[]],i=t.length>0?t[t.length-1]:null,s={version:"0.2.0",area_id:this._selectedRoom,room_config:{climate_mode:e==null?void 0:e.climate_mode,has_thermostats:(((a=e==null?void 0:e.thermostats)==null?void 0:a.length)||0)>0,has_acs:(((r=e==null?void 0:e.acs)==null?void 0:r.length)||0)>0,has_temp_sensor:!!(e!=null&&e.temperature_sensor),has_window_sensors:(((p=e==null?void 0:e.window_sensors)==null?void 0:p.length)||0)>0},live:(e==null?void 0:e.live)||{},model:this._data.model||{},settings:{control_mode:this.controlMode},outdoor:{temp:(i==null?void 0:i.outdoor_temp)??null}};return JSON.stringify(s,null,2)}_downloadString(e,t,i){const s=new Blob([e],{type:`${i};charset=utf-8`}),o=URL.createObjectURL(s),a=document.createElement("a");a.href=o,a.download=t,a.click(),URL.revokeObjectURL(o)}_exportCsv(){var r,p;const e=this._buildCsvString();if(!e)return;const t=(p=(r=this.hass)==null?void 0:r.areas)==null?void 0:p[this._selectedRoom],i=this.rooms[this._selectedRoom],s=((i==null?void 0:i.display_name)||(t==null?void 0:t.name)||this._selectedRoom).replace(/\s+/g,"_").toLowerCase(),o=new Date(this._rangeStart).toISOString().slice(0,10),a=new Date(this._rangeEnd).toISOString().slice(0,10);this._downloadString(e,`roommind_${s}_${o}_${a}.csv`,"text/csv"),this._openDropdown=null}_exportDiagnostics(){var o,a;const e=this._buildDiagnosticsString();if(!e)return;const t=(a=(o=this.hass)==null?void 0:o.areas)==null?void 0:a[this._selectedRoom],i=this.rooms[this._selectedRoom],s=((i==null?void 0:i.display_name)||(t==null?void 0:t.name)||this._selectedRoom).replace(/\s+/g,"_").toLowerCase();this._downloadString(e,`roommind_diagnostics_${s}.json`,"application/json"),this._openDropdown=null}_copyToClipboard(e){var t;return(t=navigator.clipboard)!=null&&t.writeText?(navigator.clipboard.writeText(e).catch(()=>{this._copyToClipboardFallback(e)}),!0):this._copyToClipboardFallback(e)}_copyToClipboardFallback(e){const t=document.createElement("textarea");t.value=e,t.style.position="fixed",t.style.opacity="0",document.body.appendChild(t),t.select();let i=!1;try{i=document.execCommand("copy")}catch(s){console.debug("[RoomMind] clipboard fallback:",s)}return document.body.removeChild(t),i}_copyCsvToClipboard(){const e=this._buildCsvString();e&&(this._copyToClipboard(e),this._openDropdown=null)}_copyDiagnosticsToClipboard(){const e=this._buildDiagnosticsString();e&&(this._copyToClipboard(e),this._openDropdown=null)}_toggleDropdown(e){this._openDropdown=this._openDropdown===e?null:e}_closeDropdowns(){this._openDropdown&&(this._openDropdown=null)}_buildWsParams(){return{type:"roommind/analytics/get",area_id:this._selectedRoom,start_ts:this._rangeStart/1e3,end_ts:this._rangeEnd/1e3}}async _fetchData(){if(this._selectedRoom){this._loading=!0,this._data=null,this._chartAnchor=this._rangeEnd;try{const e=await this.hass.callWS(this._buildWsParams());this._data=e}catch(e){console.debug("[RoomMind] fetchData:",e),this._data=null}finally{this._loading=!1}}}async _silentRefresh(){if(!(!this._selectedRoom||this._loading))try{const e=await this.hass.callWS(this._buildWsParams());this._data=e,this._chartAnchor=Date.now()}catch(e){console.debug("[RoomMind] silentRefresh:",e)}}};D.styles=[Xe,O`
    :host {
      display: block;
    }

    .selector-row {
      margin-bottom: 16px;
    }

    .selector-row ha-select {
      width: 100%;
    }

    .range-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      gap: 12px;
    }

    .range-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
    }

    .range-bar {
      display: inline-flex;
      border-radius: 12px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
    }

    .range-bar > :first-child {
      border-radius: 12px 0 0 12px;
    }

    .range-bar > :last-child {
      border-radius: 0 12px 12px 0;
    }

    .range-chip {
      padding: 7px 14px;
      border: none;
      border-right: 1px solid var(--divider-color);
      background: transparent;
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
    }

    .range-chip:last-child {
      border-right: none;
    }

    .range-chip:hover:not([active]) {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
      color: var(--primary-text-color);
    }

    .range-chip[active] {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .picker-chip {
      display: flex;
      align-items: center;
      padding: 0;
      cursor: pointer;
    }

    .picker-chip ha-date-range-picker {
      --mdc-icon-size: 18px;
      --mdc-icon-button-size: 32px;
    }

    .picker-chip.picker-active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }

    .date-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      white-space: nowrap;
    }

    .date-label.custom-active {
      color: var(--primary-color);
    }

    .action-buttons {
      display: flex;
      gap: 8px;
    }

    .export-split {
      position: relative;
      display: inline-flex;
    }

    .export-btn {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 7px 14px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
      color: var(--secondary-text-color);
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-btn:hover {
      color: var(--primary-text-color);
      border-color: var(--primary-color);
    }

    .export-btn[disabled] {
      opacity: 0.4;
      cursor: default;
    }

    .arrow-icon {
      --mdc-icon-size: 14px;
      margin-left: 2px;
      margin-right: -4px;
    }

    .export-dropdown {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 4px;
      min-width: 100%;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      z-index: 10;
      overflow: hidden;
    }

    .export-dropdown button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      border: none;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      white-space: nowrap;
      --mdc-icon-size: 14px;
    }

    .export-dropdown button:hover {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.08);
    }

    .export-dropdown button + button {
      border-top: 1px solid var(--divider-color);
    }

    @media (max-width: 600px) {
      .range-row {
        flex-wrap: wrap;
      }
      .range-controls {
        flex-wrap: wrap;
      }
      .range-chip {
        padding: 6px 10px;
        font-size: 11px;
      }
    }

    ha-card {
      margin-bottom: 16px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 16px 0;
      font-size: 16px;
      font-weight: 500;
    }

    .chart-info-toggle {
      --mdc-icon-size: 20px;
    }

    .chart-info-panel {
      margin: 8px 16px 4px;
      padding: 12px 14px;
      border-radius: 8px;
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.06));
      font-size: 13px;
      line-height: 1.6;
      color: var(--secondary-text-color);
    }

    .chart-info-panel p {
      margin: 0 0 8px;
    }

    .chart-info-panel p:last-child {
      margin-bottom: 0;
    }

    .chart-info-panel strong {
      color: var(--primary-text-color);
    }

    .card-content {
      padding: 16px;
    }

    .chart-container {
      padding: 16px;
      height: 300px;
    }

    .confidence-hero {
      margin-bottom: 16px;
    }

    .confidence-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 8px;
    }

    .confidence-main {
      display: flex;
      align-items: baseline;
      gap: 8px;
    }

    .confidence-value {
      font-size: 28px;
      font-weight: 600;
      color: var(--primary-text-color);
    }

    .confidence-label {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .confidence-meta {
      display: flex;
      align-items: baseline;
      gap: 6px;
    }

    .meta-value {
      font-size: 16px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .meta-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .control-mode-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 500;
      --mdc-icon-size: 14px;
    }

    .control-mode-badge.mpc {
      background: rgba(76, 175, 80, 0.12);
      color: var(--success-color, #4caf50);
    }

    .control-mode-badge.bangbang {
      background: rgba(158, 158, 158, 0.12);
      color: var(--secondary-text-color);
    }

    .confidence-bar {
      height: 4px;
      border-radius: 2px;
      background: var(--divider-color);
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      border-radius: 2px;
      background: var(--primary-color);
      transition: width 0.6s ease;
    }

    .model-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    }

    .model-stat {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      cursor: pointer;
      transition: border-color 0.2s;
    }

    .model-stat.active {
      border-color: var(--primary-color);
    }

    .stat-content {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .model-value {
      font-size: 18px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .model-value.pending {
      opacity: 0.2;
    }

    .model-label {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .info-panel.stat-info-panel {
      margin-top: 12px;
    }

    .series-legend {
      display: flex;
      justify-content: center;
      gap: 6px;
      padding: 8px 16px 12px;
      flex-wrap: wrap;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border: none;
      border-radius: 12px;
      background: transparent;
      color: var(--primary-text-color);
      font-size: 12px;
      font-family: inherit;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .legend-item:hover {
      background: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
    }

    .legend-item.legend-hidden {
      opacity: 0.35;
    }

    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .chart-empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 200px;
      gap: 8px;
      color: var(--secondary-text-color);
      opacity: 0.5;
      --mdc-icon-size: 40px;
      font-size: 13px;
    }


    .no-data {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .no-data p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
      margin-top: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    @media (max-width: 600px) {
      .model-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
      }

      .chart-container {
        padding: 8px;
        height: 240px;
      }

      .range-buttons {
        flex-wrap: wrap;
      }
    }
  `],P([_({attribute:!1})],D.prototype,"hass",2),P([_({type:Object})],D.prototype,"rooms",2),P([_()],D.prototype,"initialRoom",2),P([_()],D.prototype,"controlMode",2),P([_({type:Boolean})],D.prototype,"useImperial",2),P([u()],D.prototype,"_selectedRoom",2),P([u()],D.prototype,"_rangeStart",2),P([u()],D.prototype,"_rangeEnd",2),P([u()],D.prototype,"_data",2),P([u()],D.prototype,"_chartAnchor",2),P([u()],D.prototype,"_loading",2),P([u()],D.prototype,"_hiddenSeries",2),P([u()],D.prototype,"_expandedStat",2),P([u()],D.prototype,"_chartInfoExpanded",2),P([u()],D.prototype,"_openDropdown",2),P([u()],D.prototype,"_activeQuick",2),D=P([U("rs-analytics")],D);var si=Object.defineProperty,oi=Object.getOwnPropertyDescriptor,z=(e,t,i,s)=>{for(var o=s>1?void 0:s?oi(t,i):t,a=e.length-1,r;a>=0;a--)(r=e[a])&&(o=(s?r(t,i,o):r(o))||o);return s&&o&&si(t,i,o),o};const ni="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",ai="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",ri="M16,11.78L20.24,4.45L21.97,5.45L16.74,14.5L10.23,10.75L5.46,19H22V21H2V3H4V17.54L9.5,8L16,11.78Z",li="M15 13V5A3 3 0 0 0 9 5V13A5 5 0 1 0 15 13M12 4A1 1 0 0 1 13 5V8H11V5A1 1 0 0 1 12 4Z";let A=class extends I{constructor(){super(...arguments),this.narrow=!1,this.route={path:""},this.panel={},this._activeTab="areas",this._rooms={},this._roomsLoaded=!1,this._selectedAreaId=null,this._analyticsRoom="",this._vacationActive=!1,this._vacationTemp=null,this._vacationUntil=null,this._hiddenRooms=[],this._showHiddenRooms=!1,this._controlMode="bangbang",this._presenceEnabled=!1,this._anyoneHome=!0,this._presencePersons=[],this._saveStatus="idle",this._routeApplied=!1,this._areaInfosCache=[],this._onSaveStatus=e=>{e.stopPropagation(),this._saveStatusTimeout&&clearTimeout(this._saveStatusTimeout),this._saveStatus=e.detail.status,e.detail.status==="saved"&&(this._saveStatusTimeout=setTimeout(()=>{this._saveStatus="idle"},2e3))}}get _useImperial(){var e,t,i;return((i=(t=(e=this.hass)==null?void 0:e.config)==null?void 0:t.unit_system)==null?void 0:i.temperature)==="°F"}connectedCallback(){super.connectedCallback(),Yt(),this._loadRooms(),this._refreshInterval=setInterval(()=>this._loadRooms(),5e3),this.addEventListener("save-status",this._onSaveStatus),this._routeApplied||(this._applyRoute(),this._routeApplied=!0)}disconnectedCallback(){super.disconnectedCallback(),this._refreshInterval&&(clearInterval(this._refreshInterval),this._refreshInterval=void 0),this._saveStatusTimeout&&clearTimeout(this._saveStatusTimeout),this.removeEventListener("save-status",this._onSaveStatus)}render(){var o,a,r;const e=this.hass.language,t=!!this._selectedAreaId,i=t?(a=(o=this.hass)==null?void 0:o.areas)==null?void 0:a[this._selectedAreaId]:null,s={areas:n("panel.tab.rooms",e),analytics:n("tabs.analytics",e),settings:n("panel.tab.settings",e)};return l`
      <div class="toolbar">
        ${t?l`<ha-icon-button
              .path=${ni}
              @click=${this._onBackFromDetail}
            ></ha-icon-button>`:l`<ha-menu-button
              .hass=${this.hass}
              .narrow=${this.narrow}
            ></ha-menu-button>`}
        <div class="title">
          ${t?((r=this._rooms[this._selectedAreaId])==null?void 0:r.display_name)||(i==null?void 0:i.name)||"":n("panel.title",e)}
        </div>
        ${this._renderSaveIndicator()}
        ${t&&this._rooms[this._selectedAreaId]?l`<ha-icon-button
              .path=${ri}
              @click=${this._onGoToAnalytics}
            ></ha-icon-button><ha-icon-button
              .path=${ai}
              @click=${this._onDeleteRoom}
            ></ha-icon-button>`:h}
        ${!t&&this._activeTab==="analytics"&&this._analyticsRoom?l`<ha-icon-button
              .path=${li}
              @click=${this._onGoToRoomFromAnalytics}
            ></ha-icon-button>`:h}
      </div>

      ${t?h:l`
            <div class="tabs">
              ${Object.keys(s).map(p=>l`
                  <button
                    class="tab"
                    ?active=${this._activeTab===p}
                    @click=${()=>this._onTabClicked(p)}
                  >
                    ${s[p]}
                  </button>
                `)}
            </div>
          `}

      <div class="content">${this._renderTab()}</div>
    `}_renderTab(){switch(this._activeTab){case"areas":return this._renderAreas();case"analytics":return l`<rs-analytics
          .hass=${this.hass}
          .rooms=${this._rooms}
          .initialRoom=${this._analyticsRoom}
          .controlMode=${this._controlMode}
          .useImperial=${this._useImperial}
          @room-selected=${this._onAnalyticsRoomSelected}
        ></rs-analytics>`;case"settings":return this._renderSettings();default:return h}}_renderAreas(){var p,c;if(this._selectedAreaId){const d=(c=(p=this.hass)==null?void 0:p.areas)==null?void 0:c[this._selectedAreaId];if(d){const g=this._rooms[this._selectedAreaId]??null;return l`
          <rs-room-detail
            .area=${d}
            .config=${g}
            .hass=${this.hass}
            .presenceEnabled=${this._presenceEnabled}
            .presencePersons=${this._presencePersons}
            .useImperial=${this._useImperial}
            @back-clicked=${this._onBackFromDetail}
            @room-updated=${this._onRoomUpdated}
          ></rs-room-detail>
        `}this._selectedAreaId=null}if(!this._roomsLoaded)return l`<div class="loading">${n("panel.loading",this.hass.language)}</div>`;const e=this._areaInfosCache,t=e.filter(d=>!this._hiddenRooms.includes(d.area.area_id)),i=e.filter(d=>this._hiddenRooms.includes(d.area.area_id));if(e.length===0)return l`
        <div class="placeholder">
          <ha-icon icon="mdi:home" style="--mdc-icon-size: 56px; opacity: 0.4"></ha-icon>
          <p>${n("panel.no_areas",this.hass.language)}<br/>${n("panel.no_areas_hint",this.hass.language)}</p>
        </div>
      `;const s=t.filter(d=>d.config).length,o=t.filter(d=>{var g,m;return((m=(g=d.config)==null?void 0:g.live)==null?void 0:m.mode)==="heating"}).length,a=t.filter(d=>{var g,m;return((m=(g=d.config)==null?void 0:g.live)==null?void 0:m.mode)==="cooling"}).length,r=this.hass.language;return l`
      ${s>0||i.length>0?l`
            <ha-card class="stats-bar">
              ${s>0?l`
                <div class="stat">
                  <span class="stat-value">${s}</span>
                  <span class="stat-label">${n("panel.stat.rooms",r)}</span>
                </div>
                <div class="stat">
                  <span class="stat-value" style="color: var(--warning-color, #ff9800)">${o}</span>
                  <span class="stat-label">${n("panel.stat.heating",r)}</span>
                </div>
                <div class="stat">
                  <span class="stat-value" style="color: var(--info-color, #2196f3)">${a}</span>
                  <span class="stat-label">${n("panel.stat.cooling",r)}</span>
                </div>
              `:h}
              ${i.length>0?l`<ha-icon-button
                    class="hidden-rooms-toggle"
                    .path=${Je}
                    @click=${()=>{this._showHiddenRooms=!this._showHiddenRooms}}
                  ></ha-icon-button>`:h}
            </ha-card>
          `:h}

      ${this._showHiddenRooms&&i.length>0?l`
            <ha-card class="hidden-rooms-panel">
              <div class="hidden-rooms-header">
                <span>${n("panel.hidden_rooms",r)} (${i.length})</span>
              </div>
              ${i.map(d=>l`
                <div class="hidden-room-row">
                  <span class="hidden-room-name">${d.area.name}</span>
                  <ha-button @click=${()=>this._unhideRoom(d.area.area_id)}>
                    ${n("panel.unhide",r)}
                  </ha-button>
                </div>
              `)}
            </ha-card>
          `:h}

      ${this._vacationActive&&this._vacationTemp!==null?l`
            <ha-card class="vacation-banner">
              <div class="vacation-content">
                <ha-icon icon="mdi:airplane"></ha-icon>
                <div class="vacation-text">
                  <span class="vacation-title">${n("vacation.banner_title",this.hass.language)}</span>
                  <span class="vacation-detail">${n("vacation.banner_detail",this.hass.language,{temp:this._vacationTemp.toFixed(1),unit:C(this._useImperial),date:this._vacationUntil?new Date(this._vacationUntil*1e3).toLocaleString(this.hass.language,{dateStyle:"medium",timeStyle:"short"}):"—"})}</span>
                </div>
                <ha-button @click=${this._clearVacation}>
                  ${n("vacation.deactivate",this.hass.language)}
                </ha-button>
              </div>
            </ha-card>
          `:h}

      ${this._presenceEnabled&&!this._anyoneHome?l`
            <ha-card class="presence-banner">
              <div class="vacation-content">
                <ha-icon icon="mdi:home-off-outline"></ha-icon>
                <div class="vacation-text">
                  <span class="vacation-title">${n("presence.banner_title",this.hass.language)}</span>
                  <span class="vacation-detail">${n("presence.banner_detail",this.hass.language)}</span>
                </div>
              </div>
            </ha-card>
          `:h}

      <div class="area-grid">
        ${t.map(d=>l`
            <rs-area-card
              .area=${d.area}
              .config=${d.config}
              .climateEntityCount=${d.climateEntityCount}
              .tempSensorCount=${d.tempSensorCount}
              .hass=${this.hass}
              .controlMode=${this._controlMode}
              .useImperial=${this._useImperial}
              @area-selected=${this._onAreaSelected}
              @hide-room=${this._onHideRoom}
            ></rs-area-card>
          `)}
      </div>
    `}_renderSettings(){return l`<rs-settings .hass=${this.hass} .rooms=${this._rooms} .useImperial=${this._useImperial}></rs-settings>`}_computeAreaInfos(){var i;if(!((i=this.hass)!=null&&i.areas))return[];const t=Object.values(this.hass.areas).map(s=>{const o=Ge(s.area_id,this.hass.entities,this.hass.devices),a=o.filter(p=>p.entity_id.startsWith("climate.")).length,r=o.filter(p=>{var c,d;return p.entity_id.startsWith("sensor.")&&((d=(c=this.hass.states[p.entity_id])==null?void 0:c.attributes)==null?void 0:d.device_class)==="temperature"}).length;return{area:s,config:this._rooms[s.area_id]??null,climateEntityCount:a,tempSensorCount:r}});return t.sort((s,o)=>{const a=s.config?2:s.climateEntityCount>0?1:0,r=o.config?2:o.climateEntityCount>0?1:0;return a!==r?r-a:s.area.name.localeCompare(o.area.name)}),t}async _loadRooms(){try{const e=await this.hass.callWS({type:"roommind/rooms/list"});this._rooms=e.rooms,this._vacationActive=e.vacation_active??!1,this._vacationTemp=e.vacation_temp??null,this._vacationUntil=e.vacation_until??null,this._hiddenRooms=e.hidden_rooms??[],this._controlMode=e.control_mode??"bangbang",this._presenceEnabled=e.presence_enabled??!1,this._anyoneHome=e.anyone_home??!0,this._presencePersons=e.presence_persons??[]}catch(e){console.debug("[RoomMind] loadRooms:",e)}finally{this._roomsLoaded=!0}}_onBackFromDetail(){this._selectedAreaId=null,this._navigate("")}async _onDeleteRoom(){var t,i;if(!this._selectedAreaId)return;const e=(i=(t=this.hass)==null?void 0:t.areas)==null?void 0:i[this._selectedAreaId];if(e&&confirm(n("room.confirm_delete",this.hass.language,{name:e.name})))try{await this.hass.callWS({type:"roommind/rooms/delete",area_id:this._selectedAreaId}),this._selectedAreaId=null,this._navigate(""),this._loadRooms()}catch(s){console.debug("[RoomMind] deleteRoom:",s)}}_onTabClicked(e){this._activeTab=e,this._selectedAreaId=null,e==="areas"?this._navigate(""):this._navigate(`/${e}`)}_onAreaSelected(e){this._selectedAreaId=e.detail.areaId,this._navigate(`/room/${e.detail.areaId}`)}async _onHideRoom(e){const t=[...new Set([...this._hiddenRooms,e.detail.areaId])];this._hiddenRooms=t;try{await this.hass.callWS({type:"roommind/settings/save",hidden_rooms:t})}catch(i){console.debug("[RoomMind] hideRoom:",i)}}async _unhideRoom(e){const t=this._hiddenRooms.filter(i=>i!==e);this._hiddenRooms=t,t.length===0&&(this._showHiddenRooms=!1);try{await this.hass.callWS({type:"roommind/settings/save",hidden_rooms:t})}catch(i){console.debug("[RoomMind] unhideRoom:",i)}}_onGoToAnalytics(){this._selectedAreaId&&(this._analyticsRoom=this._selectedAreaId,this._selectedAreaId=null,this._activeTab="analytics",this._navigate(`/analytics/${this._analyticsRoom}`))}_onGoToRoomFromAnalytics(){this._analyticsRoom&&(this._selectedAreaId=this._analyticsRoom,this._activeTab="areas",this._navigate(`/room/${this._analyticsRoom}`))}_onAnalyticsRoomSelected(e){this._analyticsRoom=e.detail.areaId,this._navigate(`/analytics/${e.detail.areaId}`)}async _clearVacation(){try{await this.hass.callWS({type:"roommind/settings/save",vacation_until:null}),this._vacationActive=!1,this._vacationTemp=null,this._vacationUntil=null}catch(e){console.debug("[RoomMind] clearVacation:",e)}}_onRoomUpdated(){this._loadRooms()}_renderSaveIndicator(){if(this._saveStatus==="idle")return h;const e=this.hass.language,t=this._saveStatus==="saving"?"mdi:content-save-outline":this._saveStatus==="saved"?"mdi:check":"mdi:alert-circle-outline",i=this._saveStatus==="saving"?n("settings.saving",e):this._saveStatus==="saved"?n("settings.saved",e):n("settings.error",e);return l`
      <span class="save-indicator ${this._saveStatus}">
        <ha-icon .icon=${t}></ha-icon>
        ${i}
      </span>
    `}willUpdate(e){e.has("route")&&this._routeApplied&&this._applyRoute(),(e.has("_rooms")||e.has("hass"))&&(this._areaInfosCache=this._computeAreaInfos())}updated(e){e.has("hass")&&this.hass&&!this._roomsLoaded&&this._loadRooms()}_navigate(e){history.replaceState(null,"",`/roommind${e}`),window.dispatchEvent(new Event("location-changed"))}_applyRoute(){var t;const e=((t=this.route)==null?void 0:t.path)??"";e.startsWith("/room/")?(this._activeTab="areas",this._selectedAreaId=decodeURIComponent(e.slice(6))):e.startsWith("/analytics/")?(this._activeTab="analytics",this._selectedAreaId=null,this._analyticsRoom=decodeURIComponent(e.slice(11))):e==="/analytics"?(this._activeTab="analytics",this._selectedAreaId=null,this._analyticsRoom=""):e==="/settings"?(this._activeTab="settings",this._selectedAreaId=null):(this._activeTab="areas",this._selectedAreaId=null)}};A.styles=O`
    :host {
      display: block;
      font-family: var(--primary-font-family, Roboto, sans-serif);
      color: var(--primary-text-color);
      background: var(--primary-background-color);
      min-height: 100vh;
    }

    .toolbar {
      display: flex;
      align-items: center;
      height: 56px;
      padding: 0 12px;
      font-size: 20px;
      background-color: var(--app-header-background-color, var(--primary-background-color));
      color: var(--app-header-text-color, var(--primary-text-color));
      border-bottom: 1px solid var(--divider-color);
      box-sizing: border-box;
      position: sticky;
      top: 0;
      z-index: 4;
    }

    .toolbar .title {
      margin-left: 4px;
      font-weight: 400;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .toolbar ha-icon-button {
      color: var(--app-header-text-color, var(--primary-text-color));
    }

    .save-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 400;
      margin-right: 8px;
      opacity: 1;
      transition: opacity 0.3s ease;
    }

    .save-indicator.fade-out {
      opacity: 0;
    }

    .save-indicator ha-icon {
      --mdc-icon-size: 18px;
    }

    .save-indicator.saving {
      color: var(--primary-color, #03a9f4);
    }

    .save-indicator.saved {
      color: var(--success-color, #4caf50);
    }

    .save-indicator.error {
      color: var(--error-color, #d32f2f);
    }

    .tabs {
      display: flex;
      gap: 0;
      border-bottom: 1px solid var(--divider-color);
      padding: 0 16px;
      background: var(--primary-background-color);
      position: sticky;
      top: 56px;
      z-index: 3;
    }

    .tab {
      padding: 12px 24px;
      cursor: pointer;
      border: none;
      background: none;
      color: var(--secondary-text-color);
      font-size: 14px;
      font-weight: 500;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
      font-family: inherit;
    }

    .tab:hover {
      color: var(--primary-text-color);
    }

    .tab[active] {
      color: var(--primary-color);
      border-bottom-color: var(--primary-color);
    }

    .content {
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
      box-sizing: border-box;
    }

    @media (max-width: 600px) {
      .content {
        padding: 16px;
      }
    }

    .placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }

    .placeholder ha-icon {
      margin-bottom: 16px;
    }

    .placeholder p {
      font-size: 15px;
      max-width: 400px;
      line-height: 1.5;
    }

    .area-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(360px, 100%), 1fr));
      gap: 16px;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 80px 16px;
      color: var(--secondary-text-color);
      font-size: 14px;
    }

    .vacation-banner {
      margin-bottom: 20px;
      border-left: 4px solid var(--info-color, #2196f3);
    }

    .presence-banner {
      margin-bottom: 20px;
      border-left: 4px solid var(--info-color, #2196f3);
    }

    .vacation-content {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 12px 16px;
    }

    .vacation-content > ha-icon {
      --mdc-icon-size: 28px;
      color: var(--info-color, #2196f3);
      flex-shrink: 0;
    }

    .vacation-text {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 0;
    }

    .vacation-title {
      font-weight: 500;
      font-size: 14px;
    }

    .vacation-detail {
      font-size: 13px;
      color: var(--secondary-text-color);
    }

    .stats-bar {
      display: flex;
      align-items: center;
      gap: 24px;
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .hidden-rooms-toggle {
      margin-left: auto;
      --mdc-icon-button-size: 36px;
      --mdc-icon-size: 20px;
      color: var(--secondary-text-color);
    }

    .hidden-rooms-panel {
      margin-bottom: 20px;
      padding: 12px 16px;
    }

    .hidden-rooms-header {
      font-size: 13px;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .hidden-room-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 0;
    }

    .hidden-room-name {
      font-size: 14px;
      color: var(--primary-text-color);
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .stat-value {
      font-size: 20px;
      font-weight: 500;
      color: var(--primary-text-color);
    }

    .stat-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
  `,z([_({attribute:!1})],A.prototype,"hass",2),z([_({type:Boolean,reflect:!0})],A.prototype,"narrow",2),z([_({type:Object})],A.prototype,"route",2),z([_({type:Object})],A.prototype,"panel",2),z([u()],A.prototype,"_activeTab",2),z([u()],A.prototype,"_rooms",2),z([u()],A.prototype,"_roomsLoaded",2),z([u()],A.prototype,"_selectedAreaId",2),z([u()],A.prototype,"_analyticsRoom",2),z([u()],A.prototype,"_vacationActive",2),z([u()],A.prototype,"_vacationTemp",2),z([u()],A.prototype,"_vacationUntil",2),z([u()],A.prototype,"_hiddenRooms",2),z([u()],A.prototype,"_showHiddenRooms",2),z([u()],A.prototype,"_controlMode",2),z([u()],A.prototype,"_presenceEnabled",2),z([u()],A.prototype,"_anyoneHome",2),z([u()],A.prototype,"_presencePersons",2),z([u()],A.prototype,"_saveStatus",2),A=z([U("roommind-panel")],A)})();
